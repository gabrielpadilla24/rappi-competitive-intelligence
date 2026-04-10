"""
Uber Eats scraper implementation.
Scrapes restaurant data from ubereats.com/mx using Playwright.
"""

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
from config.locations import Location
from config.products import Product, TargetRestaurant
from config.settings import (
    PLATFORM_URLS,
    PAGE_LOAD_TIMEOUT,
    ELEMENT_TIMEOUT,
)


class UberEatsScraper(BaseScraper):
    """Scraper for Uber Eats Mexico (ubereats.com/mx)."""

    def __init__(self):
        super().__init__(platform_name="ubereats")
        self._playwright = None
        self._current_restaurant_url: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Initialize Playwright browser with stealth mode."""
        from playwright.async_api import async_playwright
        self.logger.info("Starting Uber Eats browser")
        self._playwright = await async_playwright().start()
        self.browser, self.context, self.page = await setup_stealth_browser(
            self._playwright
        )
        self.logger.info("Uber Eats browser ready")

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
        self.logger.info("Uber Eats browser closed")

    # ------------------------------------------------------------------
    # set_location
    # ------------------------------------------------------------------

    async def set_location(self, location: Location) -> bool:
        """
        Navigate to Uber Eats and set the delivery address.
        Returns True if the location was accepted.
        """
        try:
            base_url = PLATFORM_URLS["ubereats"]["feed"]
            self.logger.info(f"Navigating to {base_url}")
            await self.page.goto(base_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            await random_delay(2, 4)

            # Try to find and interact with the address input
            address_set = await self._fill_address_input(location.address)
            if not address_set:
                self.logger.warning("Could not set address via input — trying URL approach")
                return await self._set_location_via_url(location)

            self.logger.info(f"Location set: {location.short_name}")
            return True

        except Exception as e:
            self.logger.error(f"set_location failed: {e}")
            return False

    async def _fill_address_input(self, address: str) -> bool:
        """Try to type address into the autocomplete input and pick the first suggestion."""
        input_selectors = [
            'input[data-testid="address-input"]',
            'input[placeholder*="dirección"]',
            'input[placeholder*="address"]',
            'input[placeholder*="Ingresa"]',
            'input[type="text"][aria-autocomplete]',
        ]

        input_el = None
        for selector in input_selectors:
            try:
                input_el = await self.page.wait_for_selector(selector, timeout=5000)
                if input_el:
                    self.logger.debug(f"Found address input with selector: {selector}")
                    break
            except Exception:
                continue

        if not input_el:
            self.logger.warning("No address input found on page")
            return False

        try:
            await input_el.click()
            await human_like_delay()
            await input_el.fill("")
            await self.page.keyboard.type(address, delay=80)
            await random_delay(1.5, 2.5)

            # Wait for autocomplete suggestions
            suggestion_selectors = [
                'li[data-testid]',
                '[role="option"]',
                '[role="listbox"] li',
                'ul li',
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
                self.logger.warning("No autocomplete suggestions appeared")
                return False

            await suggestion_el.click()
            await random_delay(2, 3)
            return True

        except Exception as e:
            self.logger.warning(f"Address input interaction failed: {e}")
            return False

    async def _set_location_via_url(self, location: Location) -> bool:
        """Fallback: set location by navigating to the feed URL directly."""
        try:
            # Uber Eats encodes location in the 'pl' query param, but without a valid
            # encoded value we just navigate to the feed and hope cookies/IP match.
            # This is a best-effort fallback.
            self.logger.info("Using feed URL fallback for location")
            await self.page.goto(
                PLATFORM_URLS["ubereats"]["feed"],
                timeout=PAGE_LOAD_TIMEOUT,
                wait_until="domcontentloaded",
            )
            await random_delay(2, 3)
            # Check that the page loaded something useful
            content = await self.page.content()
            return "ubereats" in self.page.url
        except Exception as e:
            self.logger.error(f"URL fallback failed: {e}")
            return False

    # ------------------------------------------------------------------
    # search_restaurant
    # ------------------------------------------------------------------

    async def search_restaurant(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Search for a restaurant and navigate to its page."""
        try:
            search_url = f"https://www.ubereats.com/mx/search?q={restaurant.name}"
            self.logger.info(f"Searching: {search_url}")
            await self.page.goto(search_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            await random_delay(2, 4)
            await simulate_human_scroll(self.page, scrolls=2)

            # Look for store cards
            store_cards = await self.page.query_selector_all('a[data-testid="store-card"]')
            if not store_cards:
                store_cards = await self.page.query_selector_all('[data-testid="store-card"]')

            self.logger.info(f"Found {len(store_cards)} store cards")

            for card in store_cards:
                try:
                    # Get the card text to match against restaurant name
                    card_text = await card.text_content() or ""
                    if fuzzy_match(restaurant.search_terms, card_text):
                        self.logger.info(f"Matched restaurant card: {card_text[:80]}")
                        # Navigate to the restaurant page
                        href = await card.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = f"https://www.ubereats.com{href}"
                            self._current_restaurant_url = href
                            await self.page.goto(href, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
                            await random_delay(2, 3)
                        else:
                            await card.click()
                            await random_delay(2, 3)

                        return await self._extract_restaurant_info(restaurant)
                except Exception as e:
                    self.logger.debug(f"Card parsing error: {e}")
                    continue

            self.logger.warning(f"Restaurant '{restaurant.name}' not found in search results")
            return None

        except Exception as e:
            self.logger.error(f"search_restaurant failed: {e}")
            return None

    async def _extract_restaurant_info(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Extract name, rating, review count from the current restaurant page."""
        try:
            name = restaurant.name  # fallback
            rating = None
            review_count = None

            # Try to get the actual store name shown on page
            for name_selector in ['h1', '[data-testid="store-title"]', 'h1[class]']:
                try:
                    el = await self.page.query_selector(name_selector)
                    if el:
                        text = await el.text_content()
                        if text and text.strip():
                            name = text.strip()
                            break
                except Exception:
                    continue

            # Rating — look for numeric text near a star symbol
            rating_text = await self._find_text_by_pattern(r'\d\.\d')
            if rating_text:
                try:
                    rating = float(rating_text)
                    if rating > 5.0:
                        rating = None
                except ValueError:
                    pass

            # Review count — look for "(NNN)" or "NNN calificaciones"
            review_text = await self._find_text_by_pattern(r'\((\d+)\)')
            if review_text:
                try:
                    review_count = int(review_text)
                except ValueError:
                    pass

            self.logger.info(f"Restaurant info: name={name}, rating={rating}, reviews={review_count}")
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

            # Delivery fee — look for patterns like "$29 tarifa de envío"
            fee_patterns = [
                r'\$\s*(\d[\d,]*(?:\.\d{2})?)\s*(?:de\s+)?(?:tarifa\s+de\s+)?envío',
                r'(?:tarifa\s+de\s+)?envío[:\s]+\$\s*(\d[\d,]*(?:\.\d{2})?)',
                r'delivery\s+fee[:\s]+\$\s*(\d[\d,]*(?:\.\d{2})?)',
                r'(?:envío|delivery)\s*(?:gratis|free)',
            ]
            import re
            for pattern in fee_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    if 'gratis' in match.group(0).lower() or 'free' in match.group(0).lower():
                        delivery_info.fee_mxn = 0.0
                    else:
                        delivery_info.fee_mxn = parse_price(match.group(1))
                    break

            # Delivery time — look for "XX–YY min" or "XX min"
            time_match = re.search(r'(\d+)\s*[–\-]\s*(\d+)\s*min', page_text, re.IGNORECASE)
            if time_match:
                delivery_info.estimated_time_min = int(time_match.group(1))
                delivery_info.estimated_time_max = int(time_match.group(2))
            else:
                single_match = re.search(r'(\d+)\s*min', page_text, re.IGNORECASE)
                if single_match:
                    val = int(single_match.group(1))
                    delivery_info.estimated_time_min = val
                    delivery_info.estimated_time_max = val

            # Service fee
            svc_match = re.search(
                r'(?:tarifa\s+de\s+)?servicio[:\s]+\$\s*(\d[\d,]*(?:\.\d{2})?)',
                page_text, re.IGNORECASE
            )
            if svc_match:
                delivery_info.service_fee_mxn = parse_price(svc_match.group(1))

            self.logger.info(
                f"Delivery info: fee={delivery_info.fee_mxn}, "
                f"time={delivery_info.estimated_time_min}-{delivery_info.estimated_time_max} min"
            )

            # Return None only if we got absolutely nothing
            if (delivery_info.fee_mxn is None
                    and delivery_info.estimated_time_min is None):
                self.logger.warning("Could not extract any delivery info")
                return None

            return delivery_info

        except Exception as e:
            self.logger.error(f"get_delivery_info failed: {e}")
            return None

    # ------------------------------------------------------------------
    # get_product_price
    # ------------------------------------------------------------------

    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        """Search for a product in the restaurant menu and extract its price."""
        try:
            # Menu items on Uber Eats
            item_selectors = [
                'li[data-testid^="store-item-"]',
                '[data-testid^="menu-item"]',
                'li[data-testid*="item"]',
            ]

            items = []
            for selector in item_selectors:
                items = await self.page.query_selector_all(selector)
                if items:
                    self.logger.debug(f"Found {len(items)} items with '{selector}'")
                    break

            if not items:
                self.logger.warning("No menu items found — trying text search in page")
                return await self._product_from_page_text(product)

            for item in items:
                try:
                    item_text = await item.text_content() or ""
                    if not fuzzy_match(product.search_terms, item_text):
                        continue

                    # Extract price from rich-text spans
                    spans = await item.query_selector_all('span[data-testid="rich-text"]')
                    price = None
                    item_name = item_text.strip()

                    # First span = name, second span = price (Uber Eats convention)
                    for i, span in enumerate(spans):
                        span_text = await span.text_content() or ""
                        if i == 0:
                            item_name = span_text.strip()
                        if "$" in span_text or re.search(r'\d+\.\d{2}', span_text):
                            price = parse_price(span_text)
                            if price:
                                break

                    if price is None:
                        # Fallback: regex on full item text
                        price_match = re.search(r'\$\s*(\d[\d,]*(?:\.\d{2})?)', item_text)
                        if price_match:
                            price = parse_price(price_match.group(1))

                    self.logger.info(
                        f"Product match: '{item_name}' → ${price} (looking for {product.name})"
                    )
                    return ProductResult(
                        name=product.name,
                        reference_id=product.id,
                        price_mxn=price,
                        available=price is not None,
                        original_name=item_name,
                    )

                except Exception as e:
                    self.logger.debug(f"Item parse error: {e}")
                    continue

            self.logger.warning(f"Product '{product.name}' not found in menu items")
            return None

        except Exception as e:
            self.logger.error(f"get_product_price failed: {e}")
            return None

    async def _product_from_page_text(self, product: Product) -> Optional[ProductResult]:
        """Last-resort: scan full page text for product name + price."""
        import re
        try:
            page_text = await self.page.text_content("body") or ""
            for term in product.search_terms:
                # Look for "Big Mac $89" or "$89 Big Mac" within 60 chars
                pattern = re.escape(term) + r'.{0,60}?\$\s*(\d[\d,]*(?:\.\d{2})?)'
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    price = parse_price(match.group(1))
                    if price:
                        self.logger.info(f"Found price via page text: {term} → ${price}")
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
        """Extract visible promotions from the restaurant page."""
        promotions: list[PromotionInfo] = []
        try:
            promo_selectors = [
                '[data-baseweb="tag"]',
                '[data-testid*="promo"]',
                '[data-testid*="offer"]',
                'span[class*="promo"]',
                'div[class*="offer"]',
                'div[class*="discount"]',
            ]

            promo_keywords = ["off", "descuento", "gratis", "free", "2x1", "%", "envío gratis"]

            seen_texts: set[str] = set()

            for selector in promo_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for el in elements:
                        text = (await el.text_content() or "").strip()
                        if not text or text in seen_texts:
                            continue
                        text_lower = text.lower()
                        if any(kw in text_lower for kw in promo_keywords):
                            seen_texts.add(text)
                            promotions.append(PromotionInfo(
                                type="discount" if "%" in text or "off" in text_lower else "promotion",
                                description=text,
                                value=self._extract_promo_value(text),
                            ))
                except Exception:
                    continue

            self.logger.info(f"Found {len(promotions)} promotions")

        except Exception as e:
            self.logger.error(f"get_promotions failed: {e}")

        return promotions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _find_text_by_pattern(self, pattern: str) -> Optional[str]:
        """Search the page body text for a regex pattern and return first capture."""
        import re
        try:
            page_text = await self.page.text_content("body") or ""
            match = re.search(pattern, page_text)
            if match:
                return match.group(0)
        except Exception:
            pass
        return None

    def _extract_promo_value(self, text: str) -> str:
        """Try to extract a promo value like '50%', '$30', '2x1' from text."""
        import re
        patterns = [r'\d+%', r'\$\s*\d+', r'2x1', r'3x2']
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""
