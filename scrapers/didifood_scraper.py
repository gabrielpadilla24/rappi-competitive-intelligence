"""
DiDi Food scraper implementation.

NOTE: DiDi Food is primarily a mobile platform. Its web presence
(web.didiglobal.com/mx/food/) is a landing page only — no browsable
restaurant catalog is available on the web. This scraper documents
that limitation transparently and attempts a best-effort scrape if
a web interface is ever made available.

Limitations are captured in ScrapeResult.errors and data_completeness="failed".
"""

import re
from typing import Optional

from scrapers.base import (
    BaseScraper, RestaurantResult, DeliveryInfo,
    ProductResult, PromotionInfo,
)
from scrapers.utils.anti_detection import random_delay
from scrapers.utils.parsers import parse_price, parse_time_range, fuzzy_match
from config.locations import Location
from config.products import Product, TargetRestaurant
from config.settings import PAGE_LOAD_TIMEOUT, HEADLESS


_DIDI_URLS = [
    "https://www.didi-food.com/es-MX",
    "https://web.didiglobal.com/mx/food/",
    "https://food.didiglobal.com",
]

_RESTAURANT_INDICATORS = [
    "restaurante", "restaurant", "tienda", "store", "menú", "menu",
    "pedido", "order", "delivery", "mcdonald", "burger king", "oxxo",
]


class DidiFloodScraper(BaseScraper):
    """
    Scraper for DiDi Food Mexico.

    DiDi Food does not expose a web-based restaurant catalog.
    This scraper:
      1. Attempts to load known DiDi web URLs
      2. Checks for scrapeable restaurant content
      3. Returns failed results with clear error messages when blocked
    """

    def __init__(self):
        super().__init__(platform_name="didifood")
        self._playwright = None
        self._web_available: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Initialize browser with mobile emulation (DiDi Food is mobile-first)."""
        from playwright.async_api import async_playwright
        self.logger.info("Starting DiDi Food browser (mobile emulation)")
        self._playwright = await async_playwright().start()

        self.browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        # Mobile emulation — DiDi Food is designed for mobile
        iphone = self._playwright.devices["iPhone 13"]
        self.context = await self.browser.new_context(
            **iphone,
            locale="es-MX",
            timezone_id="America/Mexico_City",
            ignore_https_errors=True,
        )
        self.page = await self.context.new_page()
        self.logger.info("DiDi Food browser ready (iPhone 13 emulation)")

    async def teardown(self) -> None:
        """Close browser and release resources."""
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
    # set_location
    # ------------------------------------------------------------------

    async def set_location(self, location: Location) -> bool:
        """
        Attempt to navigate to DiDi Food and check for restaurant content.

        Returns True if the page has scrapeable restaurant data.
        Returns False (with logging) if only a landing page is found.
        """
        self.logger.warning(
            "DiDi Food web scraping is limited — the platform is primarily mobile-only. "
            "Attempting best-effort scrape."
        )

        for url in _DIDI_URLS:
            try:
                self.logger.info(f"Trying DiDi URL: {url}")
                response = await self.page.goto(
                    url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded"
                )
                await random_delay(2, 3)

                if response and response.status >= 400:
                    self.logger.warning(f"HTTP {response.status} for {url}")
                    continue

                content = await self.page.content()
                content_lower = content.lower()

                has_restaurants = any(ind in content_lower for ind in _RESTAURANT_INDICATORS)

                if has_restaurants:
                    self.logger.info(f"DiDi Food page has restaurant content at {url}")
                    self._web_available = True

                    # Try to set the address if there is an input
                    await self._try_set_address(location.address)
                    return True

                self.logger.info(f"No restaurant content at {url} (landing page only)")

            except Exception as e:
                self.logger.warning(f"Failed to load {url}: {e}")
                continue

        self.logger.error(
            "DiDi Food web is not scrapeable — no restaurant catalog found on any URL. "
            "Data collection requires the DiDi Food mobile app or an official API."
        )
        self._web_available = False
        return False

    async def _try_set_address(self, address: str) -> None:
        """Best-effort: try to fill in an address input if one exists."""
        try:
            input_el = await self.page.query_selector('input[type="text"]')
            if input_el:
                await input_el.fill(address)
                await random_delay(1, 2)
                await self.page.keyboard.press("Enter")
                await random_delay(1, 2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # search_restaurant
    # ------------------------------------------------------------------

    async def search_restaurant(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Search for a restaurant on DiDi Food web."""
        if not self._web_available:
            self.logger.warning(
                f"DiDi Food web not available — cannot search for '{restaurant.name}'"
            )
            return None

        try:
            # Best-effort: look for any restaurant-like elements
            card_selectors = [
                'a[href*="restaurant"]',
                'a[href*="store"]',
                'div[class*="store"]',
                'div[class*="restaurant"]',
            ]
            for selector in card_selectors:
                cards = await self.page.query_selector_all(selector)
                for card in cards:
                    text = await card.text_content() or ""
                    if fuzzy_match(restaurant.search_terms, text):
                        self.logger.info(f"DiDi Food match: {text[:60]}")
                        try:
                            await card.click()
                            await random_delay(2, 3)
                        except Exception:
                            pass
                        return RestaurantResult(
                            name=text.strip()[:100] or restaurant.name,
                            available=True,
                        )

            self.logger.warning(f"'{restaurant.name}' not found on DiDi Food web")
            return None

        except Exception as e:
            self.logger.error(f"search_restaurant failed on DiDi Food: {e}")
            return None

    # ------------------------------------------------------------------
    # get_delivery_info
    # ------------------------------------------------------------------

    async def get_delivery_info(self) -> Optional[DeliveryInfo]:
        """Extract delivery info from DiDi Food — likely unavailable via web."""
        if not self._web_available:
            self.logger.warning("DiDi Food web not available — no delivery info")
            return None

        try:
            page_text = await self.page.text_content("body") or ""
            delivery_info = DeliveryInfo()

            fee_match = re.search(r'\$\s*(\d[\d,]*(?:\.\d{2})?)\s*(?:de\s+)?envío', page_text, re.IGNORECASE)
            if fee_match:
                delivery_info.fee_mxn = parse_price(fee_match.group(1))
            elif re.search(r'envío\s*gratis', page_text, re.IGNORECASE):
                delivery_info.fee_mxn = 0.0

            time_min, time_max = parse_time_range(page_text)
            delivery_info.estimated_time_min = time_min
            delivery_info.estimated_time_max = time_max

            if delivery_info.fee_mxn is None and time_min is None:
                return None

            return delivery_info

        except Exception as e:
            self.logger.error(f"get_delivery_info failed on DiDi Food: {e}")
            return None

    # ------------------------------------------------------------------
    # get_product_price
    # ------------------------------------------------------------------

    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        """Look for a product price on DiDi Food — likely unavailable via web."""
        if not self._web_available:
            self.logger.warning(
                f"DiDi Food web not available — cannot get price for '{product.name}'"
            )
            return None

        try:
            page_text = await self.page.text_content("body") or ""
            for term in product.search_terms:
                pattern = re.escape(term) + r'.{0,80}?\$\s*(\d[\d,]*(?:\.\d{2})?)'
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    price = parse_price(match.group(1))
                    if price:
                        self.logger.info(f"DiDi Food product: {term} → ${price}")
                        return ProductResult(
                            name=product.name,
                            reference_id=product.id,
                            price_mxn=price,
                            available=True,
                            original_name=term,
                        )
        except Exception as e:
            self.logger.error(f"get_product_price failed on DiDi Food: {e}")

        return None

    # ------------------------------------------------------------------
    # get_promotions
    # ------------------------------------------------------------------

    async def get_promotions(self) -> list[PromotionInfo]:
        """Extract promotions from DiDi Food — best effort."""
        if not self._web_available:
            return []

        promotions: list[PromotionInfo] = []
        try:
            promo_keywords = ["off", "descuento", "gratis", "free", "2x1", "%"]
            promo_selectors = [
                'span[class*="badge"]',
                'div[class*="promo"]',
                'div[class*="discount"]',
                'span[class*="tag"]',
            ]
            seen: set[str] = set()
            for selector in promo_selectors:
                elements = await self.page.query_selector_all(selector)
                for el in elements:
                    text = (await el.text_content() or "").strip()
                    if text and text not in seen and any(kw in text.lower() for kw in promo_keywords):
                        seen.add(text)
                        promotions.append(PromotionInfo(
                            type="discount",
                            description=text,
                            value=self._extract_promo_value(text),
                        ))
        except Exception as e:
            self.logger.error(f"get_promotions failed on DiDi Food: {e}")

        return promotions

    def _extract_promo_value(self, text: str) -> str:
        for pat in [r'\d+%', r'\$\s*\d+', r'2x1']:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""
