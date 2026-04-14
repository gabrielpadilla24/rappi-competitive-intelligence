"""
Rappi scraper implementation.
Scrapes restaurant data from rappi.com.mx using Playwright with
optional network response interception for JSON data.
"""

import re
from typing import Optional

# Keywords that indicate a restaurant sub-category card (not the main branch).
# Used to prefer "McDonald's Antara" over "McDonald's Postres" when both match.
_SUBCATEGORY_KEYWORDS = frozenset({
    "postres", "desayunos", "helados", "bebidas", "café", "cafe",
    "pollos", "ensaladas", "snacks", "malteadas", "mccafé", "mccafe",
})

from scrapers.base import (
    BaseScraper, ScrapeResult, RestaurantResult, DeliveryInfo,
    ProductResult, PromotionInfo,
)
from scrapers.utils.anti_detection import (
    setup_stealth_browser,
    random_delay,
    human_like_delay,
    simulate_human_scroll,
)
from scrapers.utils.parsers import parse_price, fuzzy_match
from config.locations import Location
from config.products import Product, TargetRestaurant
from config.settings import (
    PLATFORM_URLS,
    PAGE_LOAD_TIMEOUT,
)


class RappiScraper(BaseScraper):
    """Scraper for Rappi Mexico (rappi.com.mx)."""

    def __init__(self):
        super().__init__(platform_name="rappi")
        self._playwright = None
        self._api_responses: list[dict] = []
        self._current_restaurant_url: Optional[str] = None
        self._restaurant_search_count = 0  # tracks calls to search_restaurant()
        self._on_subcategory_store: bool = False  # True when only a sub-category store was found

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Initialize Playwright browser with stealth mode and API interception."""
        from playwright.async_api import async_playwright
        self.logger.info("Starting Rappi browser")
        self._playwright = await async_playwright().start()
        self.browser, self.context, self.page = await setup_stealth_browser(
            self._playwright
        )
        # Intercept API responses that likely contain restaurant/menu data
        self.page.on("response", self._capture_api_response)
        self.logger.info("Rappi browser ready")

    async def teardown(self) -> None:
        """Close browser and release Playwright resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            self.logger.warning(f"Error during teardown: {e}")
        self.logger.info("Rappi browser closed")

    async def _capture_api_response(self, response) -> None:
        """Background handler: capture JSON API responses for later use."""
        url = response.url
        api_keywords = ["restaurants", "store", "menu", "search", "catalog", "product"]
        if not any(kw in url for kw in api_keywords):
            return
        try:
            body = await response.json()
            self._api_responses.append({"url": url, "data": body})
            self.logger.debug(f"Captured API response: {url[:80]}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # High-level orchestration override
    # ------------------------------------------------------------------

    async def scrape_restaurant_at_location(
        self,
        location,
        restaurant,
        products,
    ) -> ScrapeResult:
        """
        Override BaseScraper to post-process subcategory-store results.

        When only a sub-category store (e.g. "McDonalds Postres") was found and
        none of the target products exist there, the result should be a clean
        'failed' — not 'partial' with misleading delivery data from the wrong
        store.
        """
        self._on_subcategory_store = False
        result = await super().scrape_restaurant_at_location(location, restaurant, products)

        if self._on_subcategory_store and all(not p.available for p in result.products):
            result.data_completeness = "failed"
            result.delivery = None  # delivery info from a wrong store is meaningless
            if not any("sub-category" in e for e in result.errors):
                result.errors.append(
                    "Only sub-category store found (no main branch in delivery zone); "
                    "product data unavailable"
                )

        return result

    # ------------------------------------------------------------------
    # set_location
    # ------------------------------------------------------------------

    def _is_subcategory_card(self, text: str) -> bool:
        """Return True if the card text indicates a sub-category store, not the main branch."""
        text_lower = text.lower()
        return any(
            re.search(r'\b' + re.escape(kw) + r'\b', text_lower)
            for kw in _SUBCATEGORY_KEYWORDS
        )

    async def set_location(self, location: Location) -> bool:
        """Navigate to Rappi and set the delivery address."""
        try:
            # Grant browser geolocation so Rappi picks up the correct coordinates
            # when it requests location permission — this is the most reliable way
            # to set location on Rappi, which often ignores the address input.
            await self.context.grant_permissions(["geolocation"])
            await self.context.set_geolocation(
                {"latitude": location.lat, "longitude": location.lng}
            )
            self.logger.info(
                f"Geolocation set: ({location.lat}, {location.lng}) for {location.short_name}"
            )

            base_url = PLATFORM_URLS["rappi"]["base"]
            self.logger.info(f"Navigating to {base_url}")
            await self.page.goto(base_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            # Wait for SPA to finish loading, then add a human-like delay
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await random_delay(5, 7)
            await simulate_human_scroll(self.page, scrolls=1)

            address_set = await self._fill_address_modal(location.address)
            if not address_set:
                # Modal didn't appear — Rappi's UI may have changed.
                # Navigate directly to /restaurantes; the browser geolocation already set
                # above will be used by Rappi to show nearby restaurants.
                self.logger.warning(
                    "Could not set address via modal — navigating to /restaurantes "
                    "with browser geolocation"
                )
                try:
                    restaurants_url = PLATFORM_URLS["rappi"]["restaurants"]
                    await self.page.goto(
                        restaurants_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded"
                    )
                    # Wait for the SPA to finish loading restaurant listings
                    try:
                        await self.page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    await random_delay(5, 7)
                    self.logger.info("Navigated to /restaurantes with browser geolocation")
                    return True
                except Exception as e:
                    self.logger.warning(f"Fallback /restaurantes navigation failed: {e}")
                return False

            self.logger.info(f"Location set: {location.short_name}")
            return True

        except Exception as e:
            self.logger.error(f"set_location failed: {e}")
            return False

    async def _fill_address_modal(self, address: str) -> bool:
        """Interact with Rappi's address modal or input field."""
        # Scroll once more to trigger any lazy-loaded modals before scanning
        await simulate_human_scroll(self.page, scrolls=1)
        await random_delay(1, 2)

        # Ordered from most specific (Rappi-specific) to most generic.
        # Includes both direct inputs and button triggers that open an input.
        modal_triggers = [
            # Rappi data-qa patterns
            '[data-qa="input-address"]',
            '[data-qa*="address-input"]',
            '[data-qa*="location-input"]',
            '[data-qa*="search-address"]',
            # Class-based inputs
            '[class*="address-search"] input',
            '[class*="AddressSearch"] input',
            '[class*="address-input"]',
            '[class*="AddressInput"]',
            '[class*="location-input"]',
            # ARIA / role patterns
            '[role="combobox"][aria-label*="irección"]',
            '[role="combobox"][aria-label*="iudad"]',
            '[role="searchbox"]',
            # Placeholder-based
            '[placeholder*="irección"]',
            '[placeholder*="Busca tu dirección"]',
            '[placeholder*="Ingresa tu dirección"]',
            '[placeholder*="¿Dónde"]',
            '[placeholder*="Ingresa"]',
            '[placeholder*="calle"]',
            '[placeholder*="Buscar"]',
            # Text-based modal triggers (buttons/labels that open the actual input)
            'text="Ingresa tu dirección"',
            'text="¿Dónde quieres recibir"',
            'text="Selecciona tu dirección"',
            'text="¿A dónde te llevamos?"',
            'text="Agregar dirección"',
            'text="Tu dirección"',
            'text="Ciudad de México"',
            # Autocomplete-based
            'input[autocomplete*="address"]',
            'input[autocomplete*="street"]',
            # Input type fallbacks
            'input[type="search"]',
            'input[type="text"]',
        ]

        input_el = None
        for selector in modal_triggers:
            try:
                input_el = await self.page.wait_for_selector(selector, timeout=4000)
                if input_el:
                    self.logger.debug(f"Found address trigger: {selector}")
                    # If it's a button/text, click to open the input
                    tag = await input_el.evaluate("el => el.tagName.toLowerCase()")
                    if tag != "input":
                        await input_el.click()
                        await human_like_delay()
                        # Now find the actual input
                        input_el = await self.page.wait_for_selector(
                            'input[type="text"]', timeout=4000
                        )
                    break
            except Exception:
                continue

        if not input_el:
            self.logger.warning("No address input found on Rappi")
            return False

        try:
            await input_el.click()
            await human_like_delay()
            await input_el.fill("")
            await self.page.keyboard.type(address, delay=90)
            await random_delay(1.5, 2.5)

            # Wait for autocomplete
            suggestion_selectors = [
                '[role="option"]',
                '[role="listbox"] li',
                'ul[role="listbox"] li',
                'div[data-qa*="suggestion"]',
                'li[class*="suggestion"]',
            ]
            suggestion_el = None
            for sel in suggestion_selectors:
                try:
                    suggestion_el = await self.page.wait_for_selector(sel, timeout=5000)
                    if suggestion_el:
                        break
                except Exception:
                    continue

            if not suggestion_el:
                self.logger.warning("No address suggestions on Rappi")
                # Try pressing Enter as fallback
                await self.page.keyboard.press("Enter")
                await random_delay(1, 2)
                return True

            await suggestion_el.click()
            await random_delay(2, 4)

            # Confirm if there is a confirm button
            confirm_selectors = [
                'button:has-text("Confirmar")',
                'button:has-text("Aceptar")',
                'button[data-qa*="confirm"]',
            ]
            for sel in confirm_selectors:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn:
                        await btn.click()
                        await random_delay(1, 2)
                        break
                except Exception:
                    continue

            return True

        except Exception as e:
            self.logger.warning(f"Address input failed: {e}")
            return False

    # ------------------------------------------------------------------
    # search_restaurant
    # ------------------------------------------------------------------

    async def search_restaurant(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Search for a restaurant and navigate to its page."""
        try:
            self._restaurant_search_count += 1
            self._on_subcategory_store = False

            # From the second restaurant onward, add a longer delay and navigate to
            # /restaurantes so the search has proper location context.
            # Using /restaurantes (not the home page) gives better search results
            # because it applies the geolocation that was set during set_location.
            if self._restaurant_search_count > 1:
                self.logger.info(
                    f"Extended anti-bot delay before restaurant "
                    f"#{self._restaurant_search_count} ({restaurant.name})"
                )
                await random_delay(8, 12)
                await self.page.goto(
                    PLATFORM_URLS["rappi"]["restaurants"],
                    timeout=PAGE_LOAD_TIMEOUT,
                    wait_until="domcontentloaded",
                )
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await random_delay(2, 4)

            # Reset captured API responses for this restaurant
            self._api_responses = []

            # Try the search bar first
            result = await self._search_via_search_bar(restaurant)
            if result:
                return result

            # Fallback: navigate to restaurants listing page
            self.logger.info("Search bar approach failed — trying restaurants feed")
            return await self._search_via_feed(restaurant)

        except Exception as e:
            self.logger.error(f"search_restaurant failed: {e}")
            return None

    async def _search_via_search_bar(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        search_selectors = [
            'input[placeholder*="Buscar"]',
            'input[placeholder*="buscar"]',
            'input[type="search"]',
            '[data-qa*="search"] input',
            'button[aria-label*="Buscar"]',
        ]
        search_el = None
        for sel in search_selectors:
            try:
                search_el = await self.page.wait_for_selector(sel, timeout=4000)
                if search_el:
                    break
            except Exception:
                continue

        if not search_el:
            return None

        try:
            tag = await search_el.evaluate("el => el.tagName.toLowerCase()")
            if tag == "button":
                await search_el.click()
                await human_like_delay()
                search_el = await self.page.wait_for_selector('input[type="text"]', timeout=3000)

            await search_el.click()
            await search_el.fill("")
            await self.page.keyboard.type(restaurant.name, delay=80)
            await random_delay(1.5, 2.5)

            # Wait for results
            await self.page.wait_for_load_state("networkidle", timeout=8000)
            await simulate_human_scroll(self.page, scrolls=1)

            return await self._find_and_navigate_to_restaurant(restaurant)

        except Exception as e:
            self.logger.debug(f"Search bar approach error: {e}")
            return None

    async def _search_via_feed(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        try:
            restaurants_url = PLATFORM_URLS["rappi"]["restaurants"]
            await self.page.goto(
                restaurants_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded"
            )
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await random_delay(2, 3)
            await simulate_human_scroll(self.page, scrolls=3)
            return await self._find_and_navigate_to_restaurant(restaurant)
        except Exception as e:
            self.logger.debug(f"Feed search error: {e}")
            return None

    async def _find_and_navigate_to_restaurant(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Scan the current page for a matching restaurant card and click it."""
        card_selectors = [
            'a[data-qa*="store"]',
            'a[data-qa*="restaurant"]',
            'div[data-qa*="store-card"]',
            'a[href*="/restaurantes/"]',
            'a[href*="/tiendas/"]',
        ]

        # Wait up to 15 s for at least one card to appear before scanning.
        # This prevents false "0 results" on pages that are still rendering.
        for selector in card_selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=15000)
                break  # at least one card type is present — proceed to scan
            except Exception:
                continue  # this selector never appeared; try the next one

        for selector in card_selectors:
            try:
                cards = await self.page.query_selector_all(selector)

                if not cards:
                    continue

                # Log all found cards at DEBUG so we can see what Rappi returns
                all_texts = []
                for card in cards:
                    t = (await card.text_content() or "").strip()
                    if t:
                        all_texts.append(t[:60])
                self.logger.debug(
                    f"Selector '{selector}' found {len(cards)} cards: {all_texts}"
                )

                # Collect matching cards
                matches: list[tuple[str, object]] = []
                for card in cards:
                    text = await card.text_content() or ""
                    if fuzzy_match(restaurant.search_terms, text):
                        matches.append((text.strip(), card))

                if not matches:
                    continue

                # Sort: non-subcategory cards first, then shorter names (more exact).
                matches.sort(key=lambda x: (self._is_subcategory_card(x[0]), len(x[0])))
                best_text, best_card = matches[0]

                if len(matches) > 1:
                    skipped = [t[:40] for t, _ in matches[1:]]
                    self.logger.debug(f"Skipped lower-ranked cards: {skipped}")

                # Warn when the only option is a sub-category store — products like
                # "Big Mac" may not appear in a "postres" or "desayunos" store.
                if self._is_subcategory_card(best_text):
                    self.logger.warning(
                        f"Best match '{best_text[:60]}' looks like a sub-category store "
                        f"(no main branch found). Proceeding anyway — product matches may fail."
                    )
                    self._on_subcategory_store = True
                else:
                    self.logger.info(f"Matched Rappi card: {best_text[:60]}")
                href = await best_card.get_attribute("href") or ""
                if href:
                    if href.startswith("/"):
                        href = f"{PLATFORM_URLS['rappi']['base']}{href}"
                    self._current_restaurant_url = href
                    await self.page.goto(
                        href, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded"
                    )
                else:
                    await best_card.click()
                await random_delay(2, 3)
                return await self._extract_restaurant_info(restaurant)
            except Exception as e:
                self.logger.debug(f"Card selector '{selector}' error: {e}")
                continue

        # Last resort: check API responses
        for response in self._api_responses:
            result = self._restaurant_from_api(response, restaurant)
            if result:
                return result

        self.logger.warning(f"Restaurant '{restaurant.name}' not found on Rappi")
        return None

    def _restaurant_from_api(
        self, response: dict, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Try to extract restaurant info from a captured API response."""
        try:
            data = response.get("data", {})
            # Handle various Rappi API response shapes
            stores = (
                data.get("stores")
                or data.get("restaurants")
                or data.get("data", {}).get("stores")
                or []
            )
            if isinstance(stores, list):
                for store in stores:
                    name = store.get("name", "")
                    if fuzzy_match(restaurant.search_terms, name):
                        return RestaurantResult(
                            name=name,
                            platform_id=str(store.get("id", "")),
                            available=True,
                            rating=store.get("qualification") or store.get("rating"),
                            review_count=store.get("numRatings") or store.get("review_count"),
                        )
        except Exception:
            pass
        return None

    async def _extract_restaurant_info(
        self, restaurant: TargetRestaurant
    ) -> RestaurantResult:
        """Extract store name and rating from the current page."""
        name = restaurant.name
        rating = None
        review_count = None

        try:
            for sel in ['h1', '[data-qa*="store-name"]', '[class*="store-name"]']:
                el = await self.page.query_selector(sel)
                if el:
                    text = await el.text_content()
                    if text and text.strip():
                        name = text.strip()
                        break
        except Exception:
            pass

        try:
            page_text = await self.page.text_content("body") or ""
            rating_match = re.search(r'\b(\d\.\d)\b', page_text)
            if rating_match:
                val = float(rating_match.group(1))
                if val <= 5.0:
                    rating = val
            review_match = re.search(r'\((\d{2,})\)', page_text)
            if review_match:
                review_count = int(review_match.group(1))
        except Exception:
            pass

        return RestaurantResult(
            name=name,
            platform_id=self._current_restaurant_url or "",
            available=True,
            rating=rating,
            review_count=review_count,
        )

    # ------------------------------------------------------------------
    # get_delivery_info
    # ------------------------------------------------------------------

    async def get_delivery_info(self) -> Optional[DeliveryInfo]:
        """Extract delivery fee and time from the restaurant page."""
        try:
            delivery_info = DeliveryInfo()

            # First try API data
            api_delivery = self._delivery_from_api()
            if api_delivery:
                return api_delivery

            page_text = await self.page.text_content("body") or ""

            # Delivery fee
            fee_patterns = [
                r'(?:envío|delivery)[:\s]*(?:gratis|free)',
                r'(?:costo\s+de\s+)?envío[:\s]+\$\s*(\d[\d,]*(?:\.\d{2})?)',
                r'\$\s*(\d[\d,]*(?:\.\d{2})?)\s*(?:de\s+)?envío',
            ]
            for pattern in fee_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    if "gratis" in match.group(0).lower() or "free" in match.group(0).lower():
                        delivery_info.fee_mxn = 0.0
                    elif match.lastindex and match.group(1):
                        delivery_info.fee_mxn = parse_price(match.group(1))
                    break

            # Delivery time
            time_match = re.search(r'(\d+)\s*[–\-]\s*(\d+)\s*min', page_text, re.IGNORECASE)
            if time_match:
                delivery_info.estimated_time_min = int(time_match.group(1))
                delivery_info.estimated_time_max = int(time_match.group(2))
            else:
                single = re.search(r'(\d+)\s*min', page_text, re.IGNORECASE)
                if single:
                    val = int(single.group(1))
                    delivery_info.estimated_time_min = val
                    delivery_info.estimated_time_max = val

            if delivery_info.fee_mxn is None and delivery_info.estimated_time_min is None:
                self.logger.warning("No delivery info found on Rappi page")
                return None

            self.logger.info(
                f"Delivery: fee={delivery_info.fee_mxn}, "
                f"time={delivery_info.estimated_time_min}-{delivery_info.estimated_time_max} min"
            )
            return delivery_info

        except Exception as e:
            self.logger.error(f"get_delivery_info failed: {e}")
            return None

    def _delivery_from_api(self) -> Optional[DeliveryInfo]:
        """Try to build DeliveryInfo from captured API responses."""
        for resp in reversed(self._api_responses):
            try:
                data = resp.get("data", {})
                store = (
                    data.get("store")
                    or data.get("restaurant")
                    or data.get("data", {}).get("store")
                )
                if not store:
                    continue
                fee = store.get("deliveryFee") or store.get("delivery_fee")
                time_min = store.get("minDeliveryTime") or store.get("min_delivery_time")
                time_max = store.get("maxDeliveryTime") or store.get("max_delivery_time")
                if fee is not None or time_min is not None:
                    return DeliveryInfo(
                        fee_mxn=float(fee) if fee is not None else None,
                        estimated_time_min=int(time_min) if time_min is not None else None,
                        estimated_time_max=int(time_max) if time_max is not None else None,
                    )
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # get_product_price
    # ------------------------------------------------------------------

    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        """Search for a product in the restaurant menu."""
        try:
            # Try API data first (cleaner)
            api_result = self._product_from_api(product)
            if api_result:
                return api_result

            # Scroll through menu to load items
            await simulate_human_scroll(self.page, scrolls=3)

            # Common Rappi menu item selectors
            item_selectors = [
                '[data-qa*="product-item"]',
                '[data-qa*="menu-item"]',
                'div[class*="product-card"]',
                'div[class*="item-card"]',
                'li[class*="product"]',
            ]

            # Collect ALL matching items across all selectors, then pick shortest name.
            dom_matches: list[tuple[str, object | None]] = []
            for selector in item_selectors:
                items = await self.page.query_selector_all(selector)
                if not items:
                    continue
                self.logger.debug(f"Found {len(items)} items with '{selector}'")
                for item in items:
                    try:
                        item_text = await item.text_content() or ""
                        if not fuzzy_match(product.search_terms, item_text):
                            continue
                        price = self._extract_price_from_text(item_text)
                        item_name = item_text.split("\n")[0].strip() if "\n" in item_text else item_text[:60].strip()
                        dom_matches.append((item_name, price))
                    except Exception as e:
                        self.logger.debug(f"Item parse error: {e}")
                        continue
                if dom_matches:
                    break  # found items with this selector, no need to try others

            if dom_matches:
                dom_matches.sort(key=lambda x: len(x[0]))
                best_name, best_price = dom_matches[0]
                if len(dom_matches) > 1:
                    skipped = [f"'{n}'" for n, _ in dom_matches[1:3]]
                    self.logger.debug(f"Shortest DOM match wins; skipped: {skipped}")
                self.logger.info(f"Rappi product match: '{best_name}' → ${best_price}")
                return ProductResult(
                    name=product.name,
                    reference_id=product.id,
                    price_mxn=best_price,
                    available=best_price is not None,
                    original_name=best_name,
                )

            # Fallback: scan page text
            return await self._product_from_page_text(product)

        except Exception as e:
            self.logger.error(f"get_product_price failed: {e}")
            return None

    def _product_from_api(self, product: Product) -> Optional[ProductResult]:
        """
        Try to find product price in captured API responses.
        Collects all matches across all responses, then returns the shortest name.
        """
        api_matches: list[tuple[str, object | None]] = []
        for resp in self._api_responses:
            try:
                data = resp.get("data", {})
                items = (
                    data.get("products")
                    or data.get("items")
                    or data.get("data", {}).get("products")
                    or []
                )
                if not isinstance(items, list):
                    continue
                for item in items:
                    name = item.get("name", "")
                    if fuzzy_match(product.search_terms, name):
                        price = item.get("price") or item.get("basePrice")
                        api_matches.append((name, float(price) if price is not None else None))
            except Exception:
                continue

        if not api_matches:
            return None

        api_matches.sort(key=lambda x: len(x[0]))
        best_name, best_price = api_matches[0]
        if len(api_matches) > 1:
            skipped = [f"'{n}'" for n, _ in api_matches[1:3]]
            self.logger.debug(f"API: shortest match wins; skipped: {skipped}")
        return ProductResult(
            name=product.name,
            reference_id=product.id,
            price_mxn=best_price,
            available=True,
            original_name=best_name,
        )

    async def _product_from_page_text(self, product: Product) -> Optional[ProductResult]:
        """Last-resort text scan for product + price."""
        try:
            page_text = await self.page.text_content("body") or ""
            for term in product.search_terms:
                pattern = re.escape(term) + r'.{0,80}?\$\s*(\d[\d,]*(?:\.\d{2})?)'
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    price = parse_price(match.group(1))
                    if price:
                        return ProductResult(
                            name=product.name,
                            reference_id=product.id,
                            price_mxn=price,
                            available=True,
                            original_name=term,
                        )
        except Exception as e:
            self.logger.debug(f"_product_from_page_text error: {e}")
        return None

    def _extract_price_from_text(self, text: str) -> Optional[float]:
        match = re.search(r'\$\s*(\d[\d,]*(?:\.\d{2})?)', text)
        if match:
            return parse_price(match.group(1))
        return None

    # ------------------------------------------------------------------
    # get_promotions
    # ------------------------------------------------------------------

    async def get_promotions(self) -> list[PromotionInfo]:
        """Extract visible promotions from the Rappi restaurant page."""
        promotions: list[PromotionInfo] = []
        try:
            promo_selectors = [
                '[data-qa*="promo"]',
                '[data-qa*="offer"]',
                '[class*="promotion"]',
                '[class*="discount"]',
                '[class*="badge"]',
                'span[class*="tag"]',
            ]
            promo_keywords = ["off", "descuento", "gratis", "free", "2x1", "%", "envío gratis", "rappi"]
            seen: set[str] = set()

            for selector in promo_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for el in elements:
                        text = (await el.text_content() or "").strip()
                        if not text or text in seen or len(text) > 200:
                            continue
                        if any(kw in text.lower() for kw in promo_keywords):
                            seen.add(text)
                            promotions.append(PromotionInfo(
                                type="discount" if "%" in text or "off" in text.lower() else "promotion",
                                description=text,
                                value=self._extract_promo_value(text),
                            ))
                except Exception:
                    continue

            self.logger.info(f"Found {len(promotions)} promotions on Rappi")
        except Exception as e:
            self.logger.error(f"get_promotions failed: {e}")
        return promotions

    def _extract_promo_value(self, text: str) -> str:
        patterns = [r'\d+%', r'\$\s*\d+', r'2x1', r'3x2']
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""
