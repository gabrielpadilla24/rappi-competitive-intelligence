"""
DiDi Food scraper implementation.

Scrapes restaurant data from didi-food.com/es-MX/food/ using Playwright.
The web app has a full restaurant catalog accessible via desktop browser.
"""

import re
from typing import Optional

from scrapers.base import (
    BaseScraper, RestaurantResult, DeliveryInfo,
    ProductResult, PromotionInfo,
)
from scrapers.utils.anti_detection import (
    setup_stealth_browser,
    random_delay,
    human_like_delay,
    simulate_human_scroll,
)
from scrapers.utils.parsers import parse_price, parse_time_range, fuzzy_match
from scrapers.utils.screenshot import capture_evidence
from config.locations import Location
from config.products import Product, TargetRestaurant
from config.settings import (
    PLATFORM_URLS,
    PAGE_LOAD_TIMEOUT,
    ELEMENT_TIMEOUT,
)

# Keywords that indicate a sub-category store, not the main branch.
_SUBCATEGORY_KEYWORDS = frozenset({
    "postres", "desayunos", "helados", "bebidas", "café", "cafe",
    "pollos", "ensaladas", "snacks", "malteadas", "mccafé", "mccafe",
    "pollos de", "postres de", "desayunos de",
})


class DididFoodScraper(BaseScraper):
    """Scraper for DiDi Food Mexico (didi-food.com/es-MX/food/)."""

    def __init__(self):
        super().__init__(platform_name="didifood")
        self._playwright = None
        self._current_restaurant_url: Optional[str] = None
        self._restaurant_search_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Initialize Playwright browser with stealth mode."""
        from playwright.async_api import async_playwright
        self.logger.info("Starting DiDi Food browser")
        self._playwright = await async_playwright().start()
        self.browser, self.context, self.page = await setup_stealth_browser(
            self._playwright
        )
        self.logger.info("DiDi Food browser ready")

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
        self.logger.info("DiDi Food browser closed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_subcategory_card(self, text: str) -> bool:
        """Return True if card text indicates a sub-category, not the main branch."""
        text_lower = text.lower()
        return any(
            re.search(r'\b' + re.escape(kw) + r'\b', text_lower)
            for kw in _SUBCATEGORY_KEYWORDS
        )

    # ------------------------------------------------------------------
    # set_location
    # ------------------------------------------------------------------

    async def set_location(self, location: Location) -> bool:
        """Navigate to DiDi Food and set delivery address."""
        try:
            # Grant geolocation so DiDi can use browser coordinates
            await self.context.grant_permissions(["geolocation"])
            await self.context.set_geolocation(
                {"latitude": location.lat, "longitude": location.lng}
            )
            self.logger.info(
                f"Geolocation set: ({location.lat}, {location.lng}) for {location.short_name}"
            )

            base_url = PLATFORM_URLS["didifood"]["base"]
            self.logger.info(f"Navigating to {base_url}")
            await self.page.goto(
                base_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded"
            )
            await random_delay(2, 4)

            await capture_evidence(
                self.page, "didifood", location.id, "home", "landing"
            )

            address_set = await self._fill_address_input(location.address)
            if not address_set:
                self.logger.warning(
                    "Could not set address on DiDi Food — checking for restaurant content"
                )
                content = await self.page.content()
                has_content = any(
                    kw in content.lower()
                    for kw in ["restaurante", "restaurant", "tienda", "menú", "menu"]
                )
                if has_content:
                    self.logger.info("DiDi Food page has restaurant content — using default location")
                    return True
                return False

            self.logger.info(f"DiDi Food location set: {location.short_name}")
            await capture_evidence(
                self.page, "didifood", location.id, "home", "after_address"
            )
            return True

        except Exception as e:
            self.logger.error(f"set_location failed: {e}")
            return False

    async def _fill_address_input(self, address: str) -> bool:
        """Type address into the DiDi Food autocomplete input and confirm."""
        # DiDi Food uses a prominent address input on the landing page
        input_selectors = [
            'input[placeholder*="dirección"]',
            'input[placeholder*="Ingresar dirección"]',
            'input[placeholder*="dirección de entrega"]',
            'input[placeholder*="address"]',
            'input[type="text"]',
            'input[type="search"]',
        ]

        input_el = None
        for selector in input_selectors:
            try:
                input_el = await self.page.wait_for_selector(selector, timeout=5000)
                if input_el:
                    self.logger.debug(f"Found address input: {selector}")
                    break
            except Exception:
                continue

        if not input_el:
            self.logger.warning("No address input found on DiDi Food")
            return False

        try:
            await input_el.click()
            await human_like_delay()
            await input_el.fill("")
            await self.page.keyboard.type(address, delay=80)
            await random_delay(1.5, 2.5)

            # Wait for autocomplete suggestions
            suggestion_selectors = [
                '[role="option"]',
                '[role="listbox"] li',
                'ul[role="listbox"] li',
                'li[class*="suggestion"]',
                'div[class*="suggestion"]',
                'div[class*="autocomplete"] li',
                'ul li',
            ]
            suggestion_el = None
            for sel in suggestion_selectors:
                try:
                    suggestion_el = await self.page.wait_for_selector(sel, timeout=4000)
                    if suggestion_el:
                        self.logger.debug(f"Autocomplete suggestion found: {sel}")
                        break
                except Exception:
                    continue

            if suggestion_el:
                await suggestion_el.click()
                await random_delay(2, 3)
            else:
                # Fallback: try the "Buscar comida" button or Enter
                self.logger.debug("No autocomplete suggestions — trying submit button / Enter")
                submit_selectors = [
                    'button:has-text("Buscar comida")',
                    'button:has-text("Buscar")',
                    'button[type="submit"]',
                ]
                clicked = False
                for sel in submit_selectors:
                    try:
                        btn = await self.page.wait_for_selector(sel, timeout=3000)
                        if btn:
                            await btn.click()
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    await self.page.keyboard.press("Enter")

            await random_delay(2, 4)
            return True

        except Exception as e:
            self.logger.warning(f"Address input interaction failed: {e}")
            return False

    # ------------------------------------------------------------------
    # search_restaurant
    # ------------------------------------------------------------------

    async def search_restaurant(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Search for a restaurant on DiDi Food and navigate to its page."""
        try:
            self._restaurant_search_count += 1

            # Anti-bot: on the 2nd+ restaurant, add delay and return to base
            if self._restaurant_search_count > 1:
                self.logger.info(
                    f"Extended anti-bot delay before restaurant "
                    f"#{self._restaurant_search_count} ({restaurant.name})"
                )
                await random_delay(8, 12)
                await self.page.goto(
                    PLATFORM_URLS["didifood"]["base"],
                    timeout=PAGE_LOAD_TIMEOUT,
                    wait_until="domcontentloaded",
                )
                await random_delay(2, 4)

            # Try search bar first
            result = await self._search_via_search_bar(restaurant)
            if result:
                return result

            # Fallback: scan current page for matching cards
            self.logger.info("Search bar approach failed — scanning page for restaurant cards")
            return await self._find_restaurant_on_page(restaurant)

        except Exception as e:
            self.logger.error(f"search_restaurant failed: {e}")
            return None

    async def _search_via_search_bar(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Try to use DiDi Food's search bar to find the restaurant."""
        search_selectors = [
            'input[placeholder*="Buscar"]',
            'input[placeholder*="buscar"]',
            'input[placeholder*="restaurante"]',
            'input[type="search"]',
            'button[aria-label*="buscar"]',
            'button[aria-label*="Buscar"]',
        ]
        search_el = None
        for sel in search_selectors:
            try:
                search_el = await self.page.wait_for_selector(sel, timeout=4000)
                if search_el:
                    self.logger.debug(f"Found search input: {sel}")
                    break
            except Exception:
                continue

        if not search_el:
            self.logger.debug("No search bar found on DiDi Food page")
            return None

        try:
            tag = await search_el.evaluate("el => el.tagName.toLowerCase()")
            if tag == "button":
                await search_el.click()
                await human_like_delay()
                search_el = await self.page.wait_for_selector(
                    'input[type="text"], input[type="search"]', timeout=3000
                )

            await search_el.click()
            await search_el.fill("")
            await self.page.keyboard.type(restaurant.name, delay=80)
            await random_delay(1.5, 2.5)
            await self.page.wait_for_load_state("networkidle", timeout=8000)
            await simulate_human_scroll(self.page, scrolls=1)

            return await self._find_restaurant_on_page(restaurant)

        except Exception as e:
            self.logger.debug(f"Search bar error: {e}")
            return None

    async def _find_restaurant_on_page(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Scan the current page for a matching restaurant card."""
        card_selectors = [
            'a[href*="restaurant"]',
            'a[href*="store"]',
            'a[href*="tienda"]',
            '[data-testid*="store-card"]',
            '[data-testid*="restaurant"]',
            'div[class*="store-card"]',
            'div[class*="restaurant-card"]',
            'div[class*="shop-card"]',
            'li[class*="restaurant"]',
        ]

        for selector in card_selectors:
            try:
                cards = await self.page.query_selector_all(selector)
                if not cards:
                    continue

                # Log all found cards at DEBUG
                all_texts = []
                for card in cards:
                    t = (await card.text_content() or "").strip()
                    if t:
                        all_texts.append(t[:60])
                self.logger.debug(
                    f"Selector '{selector}' found {len(cards)} cards: {all_texts}"
                )

                # Collect all matching cards
                matches: list[tuple[str, object]] = []
                for card in cards:
                    text = await card.text_content() or ""
                    if fuzzy_match(restaurant.search_terms, text):
                        matches.append((text.strip(), card))

                if not matches:
                    continue

                # Prefer non-subcategory, then shortest name
                matches.sort(key=lambda x: (self._is_subcategory_card(x[0]), len(x[0])))
                best_text, best_card = matches[0]

                if len(matches) > 1:
                    skipped = [t[:40] for t, _ in matches[1:]]
                    self.logger.debug(f"Skipped lower-ranked cards: {skipped}")

                if self._is_subcategory_card(best_text):
                    self.logger.warning(
                        f"Best DiDi match '{best_text[:60]}' looks like a sub-category store. "
                        f"Proceeding anyway — product matches may fail."
                    )
                else:
                    self.logger.info(f"Matched DiDi Food card: {best_text[:60]}")

                href = await best_card.get_attribute("href") or ""
                if href:
                    if href.startswith("/"):
                        href = f"https://didi-food.com{href}"
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

        self.logger.warning(f"Restaurant '{restaurant.name}' not found on DiDi Food")
        return None

    async def _extract_restaurant_info(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Extract name, rating, review count from the restaurant page."""
        try:
            name = restaurant.name
            rating = None
            review_count = None

            # Store name from h1 or data attributes
            for sel in ['h1', '[data-testid*="store-name"]', '[class*="store-name"]',
                        '[class*="restaurant-name"]', '[class*="shop-name"]']:
                try:
                    el = await self.page.query_selector(sel)
                    if el:
                        text = await el.text_content()
                        if text and text.strip():
                            name = text.strip()
                            break
                except Exception:
                    continue

            page_text = await self.page.text_content("body") or ""

            # Rating: "X.X" followed by star or "("
            rating_match = re.search(r'(\d\.\d)\s*(?:[★*☆]|\()', page_text)
            if rating_match:
                try:
                    val = float(rating_match.group(1))
                    if 0.0 < val <= 5.0:
                        rating = val
                except ValueError:
                    pass

            # Reviews: "(7,000+)" or "(700)"
            review_match = re.search(r'\((\d[\d,]*)\+?\)', page_text)
            if review_match:
                try:
                    review_count = int(review_match.group(1).replace(',', ''))
                except ValueError:
                    pass

            self.logger.info(
                f"DiDi restaurant info: name={name}, rating={rating}, reviews={review_count}"
            )
            return RestaurantResult(
                name=name,
                platform_id=self._current_restaurant_url or "",
                available=True,
                rating=rating,
                review_count=review_count,
            )

        except Exception as e:
            self.logger.error(f"_extract_restaurant_info failed: {e}")
            return RestaurantResult(name=restaurant.name, available=True)

    # ------------------------------------------------------------------
    # get_delivery_info
    # ------------------------------------------------------------------

    async def get_delivery_info(self) -> Optional[DeliveryInfo]:
        """Extract delivery fee and estimated time from the restaurant page."""
        try:
            delivery_info = DeliveryInfo()
            page_text = await self.page.text_content("body") or ""

            # ── Delivery fee ─────────────────────────────────────────────
            # Free delivery variants
            if re.search(
                r'(?:env[íi]o|delivery|costo\s+de\s+env[íi]o)\s*(?:gratis|free)',
                page_text, re.IGNORECASE
            ):
                delivery_info.fee_mxn = 0.0
            elif re.search(
                r'(?:costo\s+de\s+env[íi]o|env[íi]o).{0,40}MXN\s*0\b',
                page_text, re.IGNORECASE | re.DOTALL
            ):
                delivery_info.fee_mxn = 0.0
            else:
                fee_patterns = [
                    r'env[íi]o\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    r'tarifa\s+de\s+env[íi]o\s*[:\s•·]?\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:de\s+)?(?:tarifa\s+de\s+)?env[íi]o',
                    r'delivery\s*(?:fee)?\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    r'env[íi]o.{0,80}?\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    # MXN format
                    r'env[íi]o.{0,40}?MXN\s*(\d[\d,]*(?:\.\d{1,2})?)',
                ]
                for pattern in fee_patterns:
                    m = re.search(pattern, page_text, re.IGNORECASE | re.DOTALL)
                    if m:
                        price = parse_price(m.group(1))
                        if price is not None and price <= 80:
                            delivery_info.fee_mxn = price
                            break
                        elif price is not None:
                            self.logger.warning(
                                f"Discarding implausible delivery fee ${price} (max $80)"
                            )

            # ── Delivery time ─────────────────────────────────────────────
            time_min, time_max = parse_time_range(page_text)
            delivery_info.estimated_time_min = time_min
            delivery_info.estimated_time_max = time_max

            # ── Service fee ───────────────────────────────────────────────
            svc_patterns = [
                r'(?:tarifa\s+de\s+)?servicio\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:tarifa\s+de\s+)?servicio',
                r'service\s+fee\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
            ]
            for pat in svc_patterns:
                m = re.search(pat, page_text, re.IGNORECASE)
                if m:
                    delivery_info.service_fee_mxn = parse_price(m.group(1))
                    break

            self.logger.info(
                f"DiDi delivery info: fee={delivery_info.fee_mxn}, "
                f"time={delivery_info.estimated_time_min}-{delivery_info.estimated_time_max} min"
            )

            if delivery_info.fee_mxn is None and delivery_info.estimated_time_min is None:
                self.logger.warning("Could not extract any delivery info from DiDi Food")
                return None

            return delivery_info

        except Exception as e:
            self.logger.error(f"get_delivery_info failed: {e}")
            return None

    # ------------------------------------------------------------------
    # get_product_price
    # ------------------------------------------------------------------

    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        """Search for a product in the DiDi Food restaurant menu."""
        try:
            await simulate_human_scroll(self.page, scrolls=2)

            item_selectors = [
                '[data-testid*="product-item"]',
                '[data-testid*="menu-item"]',
                '[data-testid*="item"]',
                'div[class*="product-card"]',
                'div[class*="menu-item"]',
                'div[class*="dish-card"]',
                'li[class*="product"]',
                'li[class*="item"]',
            ]

            for selector in item_selectors:
                items = await self.page.query_selector_all(selector)
                if not items:
                    continue

                self.logger.debug(f"Found {len(items)} items with '{selector}'")

                for item in items:
                    try:
                        item_text = await item.text_content() or ""
                        item_name = item_text.strip()

                        # Try to get a cleaner name from the first line
                        if "\n" in item_text:
                            item_name = item_text.split("\n")[0].strip()

                        if not fuzzy_match(product.search_terms, item_name):
                            # Also try matching against full item text as fallback
                            if not fuzzy_match(product.search_terms, item_text):
                                continue

                        price = self._extract_price_from_element(item_text)
                        self.logger.info(
                            f"DiDi product match: '{item_name[:50]}' → ${price} "
                            f"(looking for {product.name})"
                        )
                        return ProductResult(
                            name=product.name,
                            reference_id=product.id,
                            price_mxn=price,
                            available=price is not None,
                            original_name=item_name[:100],
                        )
                    except Exception as e:
                        self.logger.debug(f"Item parse error: {e}")
                        continue

            # Last resort: scan full page text
            self.logger.debug(f"No DOM match for '{product.name}' — scanning page text")
            return await self._product_from_page_text(product)

        except Exception as e:
            self.logger.error(f"get_product_price failed: {e}")
            return None

    def _extract_price_from_element(self, text: str) -> Optional[float]:
        """Extract the first valid price from item text."""
        # Dollar sign format
        m = re.search(r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)', text)
        if m:
            return parse_price(m.group(1))
        # MXN format
        m = re.search(r'MXN\s*(\d[\d,]*(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if m:
            return parse_price(m.group(1))
        return None

    async def _product_from_page_text(self, product: Product) -> Optional[ProductResult]:
        """Last-resort: scan full page text for product name + price."""
        try:
            page_text = await self.page.text_content("body") or ""
            for term in product.search_terms:
                pattern = re.escape(term) + r'.{0,80}?\$\s*(\d[\d,]*(?:\.\d{1,2})?)'
                m = re.search(pattern, page_text, re.IGNORECASE)
                if m:
                    price = parse_price(m.group(1))
                    if price:
                        self.logger.info(
                            f"DiDi product via page text: {term} → ${price}"
                        )
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

    # ------------------------------------------------------------------
    # get_promotions
    # ------------------------------------------------------------------

    async def get_promotions(self) -> list[PromotionInfo]:
        """Extract visible promotions from the DiDi Food restaurant page."""
        promotions: list[PromotionInfo] = []
        try:
            promo_selectors = [
                '[data-testid*="promo"]',
                '[data-testid*="offer"]',
                '[data-testid*="discount"]',
                '[class*="promotion"]',
                '[class*="promo"]',
                '[class*="discount"]',
                '[class*="badge"]',
                'span[class*="tag"]',
            ]
            promo_keywords = ["off", "descuento", "gratis", "free", "2x1", "%", "envío gratis"]
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

            self.logger.info(f"Found {len(promotions)} promotions on DiDi Food")

        except Exception as e:
            self.logger.error(f"get_promotions failed: {e}")

        return promotions

    def _extract_promo_value(self, text: str) -> str:
        for pat in [r'\d+%', r'\$\s*\d+', r'2x1', r'3x2']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return ""
