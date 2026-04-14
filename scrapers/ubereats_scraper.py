"""
Uber Eats scraper implementation.
Scrapes restaurant data from ubereats.com/mx using Playwright with
network response interception for JSON data and advanced anti-detection.
"""

import re
import json
import base64
import random
import asyncio
from urllib.parse import quote
from typing import Optional

# Keywords that indicate a restaurant sub-category store (not the main branch).
# "Pollos de McDonald's" or "McDonald's Postres" should rank below "McDonald's".
_SUBCATEGORY_KEYWORDS = frozenset({
    "postres", "desayunos", "helados", "bebidas", "café", "cafe",
    "pollos", "ensaladas", "snacks", "malteadas", "mccafé", "mccafe",
    "pollos de", "postres de", "desayunos de",
})

# URL substrings that identify Uber Eats API endpoints worth intercepting.
# Matches GraphQL operations and REST endpoints that carry store/menu data.
_API_URL_KEYWORDS = (
    "getfeedv1", "getcatalog", "getstore", "getmenu",
    "graphql", "/eats/v2/", "/menu/", "/store/",
    "ubereats.com/api", "uber.com/api/graphql",
)

# Page-text signals that indicate Cloudflare or other bot-protection blocks.
# These are intentionally narrow to avoid false-positives on Uber Eats's own
# React SPA shell (which contains "enable JavaScript to run this app") or on
# generic 404/error pages.  All patterns are Cloudflare-specific phrases.
_BLOCK_SIGNALS = (
    "please stand by, while we are checking your browser",  # Cloudflare challenge body
    "ray id:",                                               # Cloudflare Ray ID footer
    "cf-browser-verification",                              # Cloudflare input id
    "you have been blocked",                                # generic hard block
    "access to this page has been denied",                  # Cloudflare Access block
    "ddos-guard",                                           # DDoS-Guard challenge
)
# Note: "just a moment" and "checking your browser" alone are omitted because
# they appear in some legitimate Uber Eats loading states.  Use page URL
# (/cdn-cgi/) as an additional Cloudflare signal checked in _is_blocked.

from scrapers.base import (
    BaseScraper, RestaurantResult, DeliveryInfo,
    ProductResult, PromotionInfo,
)
from scrapers.utils.anti_detection import (
    setup_stealth_browser,
    human_like_delay,
    simulate_human_scroll,
    simulate_mouse_movement,
)
from scrapers.utils.parsers import parse_price, fuzzy_match
from config.locations import Location
from config.products import Product, TargetRestaurant
from config.settings import (
    PLATFORM_URLS,
    PAGE_LOAD_TIMEOUT,
)


class UberEatsScraper(BaseScraper):
    """Scraper for Uber Eats Mexico (ubereats.com/mx)."""

    def __init__(self):
        super().__init__(platform_name="ubereats")
        self._playwright = None
        self._api_responses: list[dict] = []
        self._current_restaurant_url: Optional[str] = None
        self._restaurant_search_count = 0  # tracks calls to search_restaurant()
        self._consecutive_blocks = 0       # reset on successful page load
        self._pl_param: Optional[str] = None  # base64 location param, reused in search URLs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Initialize Playwright browser with stealth mode and API interception."""
        from playwright.async_api import async_playwright
        self.logger.info("Starting Uber Eats browser")
        self._playwright = await async_playwright().start()
        self.browser, self.context, self.page = await setup_stealth_browser(
            self._playwright
        )
        # Intercept API responses — PRIMARY data source.
        # Uber Eats uses GraphQL internally; intercepting responses gives clean JSON
        # without fragile DOM parsing.
        self.page.on("response", self._capture_api_response)
        self.logger.info("Uber Eats browser ready")

    async def teardown(self) -> None:
        """Close browser and release Playwright resources."""
        for attr, label in [
            ("page", "page"),
            ("context", "context"),
            ("browser", "browser"),
            ("_playwright", "playwright"),
        ]:
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                await obj.close() if attr != "_playwright" else await obj.stop()
            except Exception as e:
                self.logger.warning(f"Error closing {label}: {e}")
        self.logger.info("Uber Eats browser closed")

    # ------------------------------------------------------------------
    # API interception helpers
    # ------------------------------------------------------------------

    async def _capture_api_response(self, response) -> None:
        """
        Background handler: capture JSON from Uber Eats API responses.

        Uber Eats sends GraphQL requests for store info, catalog, and feed.
        Capturing these gives us structured data that is far more reliable
        than parsing the rendered DOM.
        """
        url = response.url.lower()
        if not any(kw in url for kw in _API_URL_KEYWORDS):
            return
        if response.status != 200:
            return
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            return
        try:
            body = await response.json()
            self._api_responses.append({"url": response.url, "data": body})
            self.logger.debug(f"Captured API response: {response.url[:100]}")
        except Exception:
            pass  # Non-JSON body or network error — skip silently

    def _clear_api_responses(self) -> None:
        """Discard stale API responses before navigating to a new restaurant."""
        self._api_responses.clear()

    # ------------------------------------------------------------------
    # Anti-detection helpers
    # ------------------------------------------------------------------

    def _gauss_secs(self, mean: float, sigma: float, lo: float, hi: float) -> float:
        """Sample Gaussian delay clamped to [lo, hi]."""
        return max(lo, min(hi, random.gauss(mean, sigma)))

    async def _gauss_delay(self, mean: float, sigma: float, lo: float, hi: float) -> None:
        """Async sleep with Gaussian-distributed duration."""
        secs = self._gauss_secs(mean, sigma, lo, hi)
        self.logger.debug(f"Gauss delay: {secs:.1f}s (μ={mean})")
        await asyncio.sleep(secs)

    def _is_subcategory_card(self, text: str) -> bool:
        """Return True if card text indicates a sub-category store, not the main branch."""
        text_lower = text.lower()
        return any(
            re.search(r'\b' + re.escape(kw) + r'\b', text_lower)
            for kw in _SUBCATEGORY_KEYWORDS
        )

    def _is_blocked(self, page_text: str, url: str = "") -> bool:
        """
        Return True if the page signals a bot-detection block.
        Also checks the page URL for Cloudflare challenge paths (/cdn-cgi/).
        Logs which signal triggered for easier debugging.
        """
        text_lower = page_text.lower()
        for signal in _BLOCK_SIGNALS:
            if signal in text_lower:
                self.logger.warning(f"Block signal matched: {signal!r}")
                return True
        if "/cdn-cgi/" in url:
            self.logger.warning(f"Block signal matched: Cloudflare URL /cdn-cgi/ in {url!r}")
            return True
        return False

    async def _handle_block(self) -> None:
        """
        Wait after a detected block.
        Uses a shorter wait in CI/test mode (UBEREATS_BLOCK_WAIT_SECS env var).
        """
        import os
        self._consecutive_blocks += 1
        default_secs = self._gauss_secs(180, 60, 120, 300)
        wait_secs = float(os.environ.get("UBEREATS_BLOCK_WAIT_SECS", default_secs))
        self.logger.warning(
            f"Block #{self._consecutive_blocks} detected — "
            f"waiting {wait_secs:.0f}s before retry"
        )
        await asyncio.sleep(wait_secs)

    # ------------------------------------------------------------------
    # set_location
    # ------------------------------------------------------------------

    def _encode_pl_param(self, location: Location) -> str:
        """
        Encode the delivery address as a base64 JSON string for the Uber Eats
        `pl=` URL parameter.  This bypasses the address-selection modal entirely,
        which reduces interaction noise and is less likely to trigger bot checks.
        """
        city_name = (
            "Ciudad de México" if location.city in ("CDMX", "Ciudad de México") else location.city
        )
        pl_data = {
            "addressId": "",
            "address": {
                "uuid": "",
                "addressId": "",
                "location": {
                    "latitude": location.lat,
                    "longitude": location.lng,
                },
                "city": city_name,
                "country": "MX",
                "formattedAddress": location.address,
            },
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(pl_data, separators=(",", ":")).encode()
        ).decode()
        return encoded

    async def set_location(self, location: Location) -> bool:
        """
        Navigate to Uber Eats and set the delivery address.

        Approach 1 (preferred): Navigate directly to feed?pl=<encoded_location>.
          This encodes the address and coordinates into the URL, skipping the
          modal entirely and minimizing interaction with the DOM.
        Approach 2 (fallback): Navigate to feed, then fill the address modal.
        Approach 3 (last resort): Rely on browser geolocation + existing session.

        Returns True if location was accepted (feed shows restaurant content).
        """
        try:
            # Set geolocation so the browser uses the correct coordinates for
            # any permission requests or geo-based fallbacks.
            await self.context.grant_permissions(["geolocation"])
            await self.context.set_geolocation(
                {"latitude": location.lat, "longitude": location.lng}
            )
            self.logger.info(
                f"Geolocation set: ({location.lat}, {location.lng}) for {location.short_name}"
            )

            self._clear_api_responses()

            # ── Approach 1: pl= encoded URL ────────────────────────────────
            try:
                pl_param = self._encode_pl_param(location)
                self._pl_param = pl_param  # persist for use in search URLs
                pl_url = f"{PLATFORM_URLS['ubereats']['feed']}?pl={pl_param}"
                self.logger.info(f"Trying pl= URL: {pl_url[:120]}…")
                # Use "load" so React has time to render the feed before we check
                await self.page.goto(
                    pl_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="load"
                )
                self.logger.info(f"Landed on: {self.page.url}")
                # Reading pause — simulates user reviewing the page
                await self._gauss_delay(3, 0.8, 2, 5)

                page_text = await self.page.text_content("body") or ""
                if self._is_blocked(page_text, self.page.url):
                    self.logger.warning("Blocked on pl= approach")
                    await self._handle_block()
                    raise RuntimeError("blocked")

                if await self._feed_has_restaurants():
                    self.logger.info(f"Location set via pl= URL: {location.short_name}")
                    self._consecutive_blocks = 0
                    return True
                self.logger.warning(
                    f"pl= URL did not show feed (landed: {self.page.url})"
                )
            except Exception as e:
                self.logger.warning(f"pl= approach failed ({e}) — falling back to address input")

            # ── Approach 2: address input modal ────────────────────────────
            self.logger.info(f"Navigating to feed: {PLATFORM_URLS['ubereats']['feed']}")
            await self.page.goto(
                PLATFORM_URLS["ubereats"]["feed"],
                timeout=PAGE_LOAD_TIMEOUT,
                wait_until="load",
            )
            self.logger.info(f"Landed on: {self.page.url}")
            await self._gauss_delay(3, 0.8, 2, 5)

            page_text = await self.page.text_content("body") or ""
            if self._is_blocked(page_text, self.page.url):
                await self._handle_block()
                return False

            address_set = await self._fill_address_input(location.address)
            if address_set:
                self.logger.info(f"Location set via address input: {location.short_name}")
                self._consecutive_blocks = 0
                return True

            # ── Approach 3: geolocation fallback ──────────────────────────
            self.logger.warning("Address input failed — relying on geolocation/session")
            has_content = await self._feed_has_restaurants()
            if has_content:
                self.logger.info("Feed has restaurant content — proceeding with geolocation")
            return has_content

        except Exception as e:
            self.logger.error(f"set_location failed: {e}")
            return False

    async def _feed_has_restaurants(self) -> bool:
        """
        Return True if the current page is showing the restaurant feed.
        Uses DOM element detection to avoid false-positives on text like
        'Agrega tu restaurante' that appears on the generic homepage.
        """
        try:
            # Best signal: an actual store card element is in the DOM
            for sel in ('[data-testid="store-card"]', '[data-testid="home-feed"]',
                        '[data-testid="feed-section"]'):
                el = await self.page.query_selector(sel)
                if el:
                    self.logger.debug(f"Feed element found: {sel}")
                    return True
            # Fallback: URL looks like a feed/search page (not the homepage)
            url = self.page.url
            is_feed_url = any(seg in url for seg in ("/mx/feed", "/mx/search", "/store/"))
            if is_feed_url:
                self.logger.debug(f"Feed URL detected: {url}")
            return is_feed_url
        except Exception:
            return False

    async def _fill_address_input(self, address: str) -> bool:
        """
        Locate the address autocomplete input, type the address with human-like
        delays, and select the first suggestion.
        Returns True if an autocomplete suggestion was successfully clicked.
        """
        input_selectors = [
            'input[data-testid="address-input"]',
            'input[placeholder*="dirección"]',
            'input[placeholder*="address"]',
            'input[placeholder*="Ingresa"]',
            'input[type="text"][aria-autocomplete]',
        ]

        # Mouse movement before looking for input — simulates scanning the page
        await simulate_mouse_movement(self.page)

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
            self.logger.warning("No address input found on page")
            return False

        try:
            # Hover before clicking — simulates natural interaction
            await input_el.hover()
            await self._gauss_delay(0.4, 0.1, 0.2, 0.8)
            await input_el.click()
            await human_like_delay()
            await input_el.fill("")

            # Type with variable per-character delay (70–120 ms)
            for char in address:
                await self.page.keyboard.type(char)
                await asyncio.sleep(random.gauss(0.09, 0.02))  # ~90ms ± jitter

            await self._gauss_delay(1.8, 0.4, 1.0, 3.0)  # wait for suggestions

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

            await suggestion_el.hover()
            await self._gauss_delay(0.3, 0.1, 0.1, 0.6)
            await suggestion_el.click()
            await self._gauss_delay(2.5, 0.6, 1.5, 4.0)
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
        """
        Search for a restaurant and navigate to its store page.

        On the 2nd+ restaurant at a location, waits 8–15 seconds (Gaussian)
        to avoid triggering rate limits from rapid successive page loads.
        Detects Cloudflare blocks and aborts after 3 consecutive blocks.
        """
        self._restaurant_search_count += 1

        # Inter-restaurant delay on subsequent searches
        if self._restaurant_search_count > 1:
            delay = self._gauss_secs(10, 2, 8, 15)
            self.logger.info(
                f"Anti-bot: waiting {delay:.1f}s between restaurants "
                f"(restaurant #{self._restaurant_search_count})"
            )
            await asyncio.sleep(delay)

        self._clear_api_responses()

        # Abort if we've been blocked too many times in a row
        if self._consecutive_blocks >= 3:
            self.logger.error(
                "3 consecutive blocks — aborting restaurant search to avoid ban"
            )
            return None

        try:
            # Mouse movement to appear as a real user browsing the page
            await simulate_mouse_movement(self.page)

            # Append pl= so location context is preserved across navigation.
            # Without it, Uber Eats redirects to the homepage if no session cookie.
            pl_suffix = f"&pl={self._pl_param}" if self._pl_param else ""
            search_url = (
                "https://www.ubereats.com/mx/search?q="
                + quote(restaurant.name)
                + pl_suffix
            )
            self.logger.info(f"Searching: {search_url}")
            await self.page.goto(
                search_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="load"
            )
            self.logger.info(f"Landed on: {self.page.url}")
            await self._gauss_delay(3, 0.7, 2, 5)  # Reading pause after load

            page_text = await self.page.text_content("body") or ""
            if self._is_blocked(page_text, self.page.url):
                await self._handle_block()
                if self._consecutive_blocks >= 3:
                    return None
                # One retry after the block wait
                await self.page.goto(
                    search_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="load"
                )
                await self._gauss_delay(3, 0.7, 2, 5)
                page_text = await self.page.text_content("body") or ""
                if self._is_blocked(page_text, self.page.url):
                    self.logger.error("Still blocked after retry — giving up")
                    return None

            # Wait for store cards to appear (search results load asynchronously)
            for card_sel in ('a[data-testid="store-card"]', '[data-testid="store-card"]'):
                try:
                    await self.page.wait_for_selector(card_sel, timeout=8000)
                    self.logger.debug(f"Store cards appeared with selector: {card_sel}")
                    break
                except Exception:
                    continue

            # Scroll to trigger lazy-loaded store cards
            await simulate_human_scroll(self.page, scrolls=2)

            # Collect matching store cards
            store_cards = await self.page.query_selector_all('a[data-testid="store-card"]')
            if not store_cards:
                store_cards = await self.page.query_selector_all('[data-testid="store-card"]')
            if not store_cards:
                # Dump a snippet of page text to aid debugging selector mismatches
                snippet = (await self.page.text_content("body") or "")[:400]
                self.logger.debug(f"Page text snippet (no cards found): {snippet!r}")

            self.logger.info(f"Found {len(store_cards)} store cards")

            matches: list[tuple[str, object]] = []
            for card in store_cards:
                try:
                    card_text = await card.text_content() or ""
                    if fuzzy_match(restaurant.search_terms, card_text):
                        matches.append((card_text.strip(), card))
                except Exception as e:
                    self.logger.debug(f"Card parse error: {e}")
                    continue

            if not matches:
                self.logger.warning(
                    f"Restaurant '{restaurant.name}' not found in search results"
                )
                return None

            # Prefer main branch over sub-category (e.g., "McDonald's" over "McDonald's Postres"),
            # then prefer shortest name as a proxy for the most-exact match.
            matches.sort(key=lambda x: (self._is_subcategory_card(x[0]), len(x[0])))
            best_text, best_card = matches[0]
            if len(matches) > 1:
                skipped = [t[:50] for t, _ in matches[1:]]
                self.logger.debug(f"Skipped lower-ranked cards: {skipped}")

            self.logger.info(f"Best match: {best_text[:80]}")

            href = await best_card.get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = f"https://www.ubereats.com{href}"
                self._current_restaurant_url = href
                # Hover before clicking to mimic human behaviour
                await best_card.hover()
                await self._gauss_delay(0.4, 0.1, 0.2, 0.8)
                await self.page.goto(
                    href, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded"
                )
            else:
                await best_card.hover()
                await self._gauss_delay(0.3, 0.1, 0.1, 0.6)
                await best_card.click()

            await self._gauss_delay(3, 0.7, 2, 5)  # Reading pause on restaurant page

            # Check for block on restaurant page
            page_text = await self.page.text_content("body") or ""
            if self._is_blocked(page_text, self.page.url):
                await self._handle_block()
                return None

            self._consecutive_blocks = 0
            return await self._extract_restaurant_info(restaurant)

        except Exception as e:
            self.logger.error(f"search_restaurant failed: {e}")
            return None

    async def _extract_restaurant_info(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Extract name, rating, and review count from the current restaurant page."""
        try:
            name = restaurant.name  # fallback
            rating = None
            review_count = None

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

            page_text = await self.page.text_content("body") or ""

            # Rating: "4.4 ★" or "4.4 (" — capture the X.X immediately before a star or parenthesis
            rating_match = re.search(r'(\d\.\d)\s*(?:[★*☆]|\()', page_text)
            if rating_match:
                try:
                    val = float(rating_match.group(1))
                    if 0.0 < val <= 5.0:
                        rating = val
                except ValueError:
                    pass

            # Reviews: "(7,000+)" or "(700)" — strip commas and "+"
            review_match = re.search(r'\((\d[\d,]*)\+?\)', page_text)
            if review_match:
                try:
                    review_count = int(review_match.group(1).replace(",", ""))
                except ValueError:
                    pass

            self.logger.info(
                f"Restaurant info: name={name!r}, rating={rating}, reviews={review_count}"
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
        """
        Extract delivery fee and estimated time from the restaurant page.

        Priority:
          1. Intercepted API responses (most reliable, structured JSON)
          2. Specific DOM selectors (testid-based, layout-specific)
          3. Full-page regex fallback (broad but fragile)
        """
        try:
            # ── 1. API responses ────────────────────────────────────────────
            api_result = self._delivery_from_api()
            if api_result and api_result.fee_mxn is not None:
                self.logger.info(
                    f"Delivery from API: fee={api_result.fee_mxn}, "
                    f"time={api_result.estimated_time_min}-{api_result.estimated_time_max} min"
                )
                return api_result

            # ── 2. DOM + page-text fallback ─────────────────────────────────
            delivery_info = DeliveryInfo()

            delivery_info.fee_mxn = await self._extract_fee_from_dom()

            page_text = await self.page.text_content("body") or ""

            if delivery_info.fee_mxn is None:
                delivery_info.fee_mxn = self._extract_fee_from_text(page_text)

            # Delivery time: "25–35 min" range or single "30 min"
            time_match = re.search(
                r'\b(\d{1,3})\s*[–\-]\s*(\d{1,3})\s*min\b', page_text, re.IGNORECASE
            )
            if time_match:
                lo, hi = int(time_match.group(1)), int(time_match.group(2))
                if 1 <= lo <= hi <= 180:
                    delivery_info.estimated_time_min = lo
                    delivery_info.estimated_time_max = hi
            if delivery_info.estimated_time_min is None:
                single_match = re.search(r'\b(\d{1,3})\s*min\b', page_text, re.IGNORECASE)
                if single_match:
                    val = int(single_match.group(1))
                    if 1 <= val <= 180:
                        delivery_info.estimated_time_min = val
                        delivery_info.estimated_time_max = val

            # Service fee (usually only visible in checkout — best-effort)
            for pat in [
                r'(?:tarifa\s+de\s+)?servicio\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:tarifa\s+de\s+)?servicio',
                r'service\s+fee\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
            ]:
                m = re.search(pat, page_text, re.IGNORECASE)
                if m:
                    delivery_info.service_fee_mxn = parse_price(m.group(1))
                    break

            self.logger.info(
                f"Delivery info: fee={delivery_info.fee_mxn}, "
                f"time={delivery_info.estimated_time_min}-{delivery_info.estimated_time_max} min"
            )

            if delivery_info.fee_mxn is None and delivery_info.estimated_time_min is None:
                self.logger.warning("Could not extract any delivery info")
                return None

            return delivery_info

        except Exception as e:
            self.logger.error(f"get_delivery_info failed: {e}")
            return None

    def _delivery_from_api(self) -> Optional[DeliveryInfo]:
        """
        Extract delivery fee and ETA from intercepted API responses.
        Handles multiple response shapes: GraphQL (data.storeInfo) and REST.
        """
        for resp in self._api_responses:
            try:
                data = resp.get("data", {})

                # Unwrap common GraphQL wrapper layers
                store = (
                    data.get("storeInfo")
                    or data.get("store")
                    or data.get("getStoreV1")
                    or data.get("storeData")
                    or (data if "deliveryFee" in data else None)
                )
                if not store and isinstance(data, dict):
                    # Try nested under a top-level key
                    for v in data.values():
                        if isinstance(v, dict) and "deliveryFee" in v:
                            store = v
                            break

                if not store:
                    continue

                raw_fee = store.get("deliveryFee") or store.get("delivery_fee")
                if raw_fee is None:
                    continue

                # Fee may be an int (cents), float (pesos), or "$29" string
                if isinstance(raw_fee, str):
                    fee = parse_price(raw_fee)
                elif isinstance(raw_fee, (int, float)):
                    # If value looks like cents (e.g. 2900 for $29 MXN), convert
                    fee = float(raw_fee) / 100 if raw_fee > 500 else float(raw_fee)
                else:
                    continue

                fee = self._validate_fee(fee, "API")

                # ETA — Uber Eats may report in seconds or minutes
                eta_min = store.get("etaMinSeconds") or store.get("deliveryTimeMin") or store.get("etaMin")
                eta_max = store.get("etaMaxSeconds") or store.get("deliveryTimeMax") or store.get("etaMax")
                if eta_min and eta_min > 200:   # likely seconds
                    eta_min = int(eta_min / 60)
                if eta_max and eta_max > 200:
                    eta_max = int(eta_max / 60)

                self.logger.info(
                    f"Delivery from API: fee={fee}, "
                    f"eta={eta_min}-{eta_max} min "
                    f"(url={resp['url'][:80]})"
                )
                return DeliveryInfo(
                    fee_mxn=fee,
                    estimated_time_min=int(eta_min) if eta_min else None,
                    estimated_time_max=int(eta_max) if eta_max else None,
                )

            except Exception as e:
                self.logger.debug(f"_delivery_from_api parse error: {e}")
                continue

        return None

    # Delivery fees in Mexico are typically $0–$49; anything above $80 is likely
    # a product price or order subtotal picked up by an overly-broad pattern.
    _MAX_DELIVERY_FEE_MXN = 80.0

    def _validate_fee(self, value: Optional[float], source: str) -> Optional[float]:
        """Return value if it's a plausible delivery fee; log and return None otherwise."""
        if value is None:
            return None
        if value > self._MAX_DELIVERY_FEE_MXN:
            self.logger.warning(
                f"Discarding implausible delivery fee ${value} from {source} "
                f"(max: ${self._MAX_DELIVERY_FEE_MXN})"
            )
            return None
        return value

    async def _extract_fee_from_dom(self) -> Optional[float]:
        """
        Try specific DOM selectors for the delivery fee widget.
        Uses fully-qualified testid names to avoid matching cart totals or item prices.
        """
        fee_selectors = [
            '[data-testid="delivery-fee"]',
            '[data-testid="deliveryFee"]',
            '[data-testid="store-delivery-fee"]',
            '[data-testid="delivery-fee-text"]',
            '[data-testid="store-fulfillment-info"]',
            '[class*="deliveryFee"]',
            '[class*="delivery-fee"]',
        ]
        for selector in fee_selectors:
            try:
                el = await self.page.query_selector(selector)
                if not el:
                    continue
                text = (await el.text_content() or "").strip()
                if not text:
                    continue
                result = self._validate_fee(self._parse_fee_text(text), f"DOM '{selector}'")
                if result is not None:
                    self.logger.debug(f"Fee from DOM '{selector}': {result}")
                    return result
            except Exception:
                continue
        return None

    def _extract_fee_from_text(self, page_text: str) -> Optional[float]:
        """
        Extract delivery fee from full page text using progressive regex patterns.
        Handles: 'Envío $29', 'Tarifa de envío $29', '$29 Delivery Fee',
                 'Envío·$29', 'Envío gratis', 'Free delivery', 'MXN29'.
        All values are validated against _MAX_DELIVERY_FEE_MXN.
        """
        # Free delivery check first
        if re.search(
            r'(?:env[íi]o|delivery|costo\s+de\s+env[íi]o)\s*(?:gratis|free)',
            page_text, re.IGNORECASE,
        ):
            return 0.0
        if re.search(r'gratis\b.{0,20}env[íi]o|free\b.{0,20}delivery', page_text, re.IGNORECASE):
            return 0.0
        if re.search(
            r'(?:costo\s+de\s+env[íi]o|env[íi]o).{0,40}MXN\s*0\b',
            page_text, re.IGNORECASE | re.DOTALL,
        ):
            return 0.0

        fee_patterns = [
            r'(?:costo\s+de\s+)?env[íi]o.{0,40}?MXN\s*(\d[\d,]*(?:\.\d{1,2})?)',
            r'MXN\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:env[íi]o|delivery|tarifa)',
            r'env[íi]o\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
            r'tarifa\s+de\s+env[íi]o\s*[:\s•·]?\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
            r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:de\s+)?(?:tarifa\s+de\s+)?env[íi]o',
            r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*delivery(?:\s+fee)?',
            r'delivery\s*(?:fee)?\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
            r'(?:env[íi]o|delivery|tarifa).{0,80}?\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
        ]
        for pattern in fee_patterns:
            m = re.search(pattern, page_text, re.IGNORECASE | re.DOTALL)
            if m:
                price = self._validate_fee(parse_price(m.group(1)), "text pattern")
                if price is not None:
                    self.logger.debug(
                        f"Fee from text pattern: {price} (matched: {m.group(0)[:60]!r})"
                    )
                    return price
        return None

    def _parse_fee_text(self, text: str) -> Optional[float]:
        """Parse a short DOM-extracted text snippet for a fee amount."""
        text_lower = text.lower()
        if "gratis" in text_lower or "free" in text_lower:
            return 0.0
        if re.search(r'MXN\s*0\b', text, re.IGNORECASE):
            return 0.0
        m = re.search(r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)', text)
        if m:
            return parse_price(m.group(1))
        m = re.search(r'MXN\s*(\d[\d,]*(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if m:
            return parse_price(m.group(1))
        return None

    # ------------------------------------------------------------------
    # get_product_price
    # ------------------------------------------------------------------

    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        """
        Search for a product in the restaurant menu and extract its price.

        Priority:
          1. Intercepted API responses (getCatalogPresentationV2 has items with names + prices)
          2. DOM menu items (li[data-testid^="store-item-"])
          3. Full-page text regex fallback
        """
        try:
            # ── 1. API responses ────────────────────────────────────────────
            api_result = self._product_from_api(product)
            if api_result:
                self.logger.info(
                    f"Product from API: '{api_result.original_name}' → ${api_result.price_mxn}"
                )
                return api_result

            # ── 2. DOM menu items ───────────────────────────────────────────
            # Scroll to load lazy-loaded menu sections before querying items
            await simulate_human_scroll(self.page, scrolls=3)
            await self._gauss_delay(1.5, 0.4, 0.8, 2.5)

            item_selectors = [
                'li[data-testid^="store-item-"]',
                '[data-testid^="menu-item"]',
                'li[data-testid*="item"]',
            ]
            items = []
            for selector in item_selectors:
                items = await self.page.query_selector_all(selector)
                if items:
                    self.logger.debug(f"Found {len(items)} menu items with '{selector}'")
                    break

            if not items:
                self.logger.warning("No menu items found — falling back to page-text search")
                return await self._product_from_page_text(product)

            for item in items:
                try:
                    item_text = await item.text_content() or ""
                    # Extract name from first rich-text span; price from subsequent spans.
                    # Matching against the resolved name avoids false positives when the
                    # container holds many items and the search term appears in a sibling.
                    spans = await item.query_selector_all('span[data-testid="rich-text"]')
                    item_name = item_text.strip()
                    price = None

                    for i, span in enumerate(spans):
                        span_text = await span.text_content() or ""
                        if i == 0:
                            item_name = span_text.strip()
                        if "$" in span_text or re.search(r'\d+\.\d{2}', span_text):
                            price = parse_price(span_text)
                            if price:
                                break

                    if not fuzzy_match(product.search_terms, item_name):
                        continue

                    # Fallback: regex on the full item container text
                    if price is None:
                        price_match = re.search(r'\$\s*(\d[\d,]*(?:\.\d{2})?)', item_text)
                        if price_match:
                            price = parse_price(price_match.group(1))

                    self.logger.info(
                        f"Product match: '{item_name}' → ${price} "
                        f"(searching for {product.name!r})"
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
            return await self._product_from_page_text(product)

        except Exception as e:
            self.logger.error(f"get_product_price failed: {e}")
            return None

    def _product_from_api(self, product: Product) -> Optional[ProductResult]:
        """
        Extract product price from intercepted API responses.
        Handles getCatalogPresentationV2 and simpler catalog formats.
        """
        for resp in self._api_responses:
            try:
                data = resp.get("data", {})
                if not isinstance(data, dict):
                    continue

                # Collect all menu items from common response shapes
                items: list[dict] = []

                # getCatalogPresentationV2 → sections → items
                catalog = (
                    data.get("catalog")
                    or data.get("menu")
                    or data.get("getCatalogPresentationV2", {})
                    or data.get("storeMenu", {})
                )
                if isinstance(catalog, dict):
                    sections = (
                        catalog.get("sections")
                        or catalog.get("categories")
                        or catalog.get("menuCategories")
                        or []
                    )
                    for section in sections:
                        items.extend(section.get("items") or [])
                    # Also try top-level items key
                    items.extend(catalog.get("items") or [])

                # Flat items key at response root
                if not items and "items" in data:
                    items = data["items"]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_name = item.get("title") or item.get("name") or ""
                    if not fuzzy_match(product.search_terms, item_name):
                        continue

                    raw_price = (
                        item.get("price")
                        or item.get("priceForDisplay")
                        or item.get("basePrice")
                        or 0
                    )
                    # Uber Eats API may return prices as cents (int) or formatted strings
                    if isinstance(raw_price, str):
                        price = parse_price(raw_price)
                    elif isinstance(raw_price, (int, float)):
                        # Heuristic: if value > 500 it's likely cents (e.g. 8900 → $89)
                        price = float(raw_price) / 100 if raw_price > 500 else float(raw_price)
                    else:
                        price = None

                    if price is not None and price <= 0:
                        price = None

                    self.logger.debug(
                        f"API product match: '{item_name}' → ${price} "
                        f"(url={resp['url'][:80]})"
                    )
                    return ProductResult(
                        name=product.name,
                        reference_id=product.id,
                        price_mxn=price,
                        available=True,
                        original_name=item_name,
                    )

            except Exception as e:
                self.logger.debug(f"_product_from_api error: {e}")
                continue

        return None

    async def _product_from_page_text(self, product: Product) -> Optional[ProductResult]:
        """Last-resort: scan full page text for product name + price proximity."""
        try:
            page_text = await self.page.text_content("body") or ""
            for term in product.search_terms:
                pattern = re.escape(term) + r'.{0,60}?\$\s*(\d[\d,]*(?:\.\d{2})?)'
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    price = parse_price(match.group(1))
                    if price:
                        self.logger.info(
                            f"Product from page text: {term!r} → ${price}"
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
        """
        Extract visible promotions from the restaurant page.

        Priority:
          1. Intercepted API responses
          2. DOM elements (tags, banners, badges)
        """
        promotions: list[PromotionInfo] = []
        try:
            # ── 1. API responses ────────────────────────────────────────────
            api_promos = self._promotions_from_api()
            if api_promos:
                self.logger.info(f"Found {len(api_promos)} promotions from API")
                return api_promos

            # ── 2. DOM fallback ─────────────────────────────────────────────
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
                                type=(
                                    "discount"
                                    if "%" in text or "off" in text_lower
                                    else "free_delivery"
                                    if "env" in text_lower and "gratis" in text_lower
                                    else "promotion"
                                ),
                                description=text,
                                value=self._extract_promo_value(text),
                            ))
                except Exception:
                    continue

            self.logger.info(f"Found {len(promotions)} promotions from DOM")

        except Exception as e:
            self.logger.error(f"get_promotions failed: {e}")

        return promotions

    def _promotions_from_api(self) -> list[PromotionInfo]:
        """Extract promotions from intercepted API responses."""
        promotions: list[PromotionInfo] = []
        seen: set[str] = set()

        for resp in self._api_responses:
            try:
                data = resp.get("data", {})
                if not isinstance(data, dict):
                    continue

                # Common API promo fields
                promo_lists = (
                    data.get("promotions")
                    or data.get("deals")
                    or data.get("discounts")
                    or (data.get("storeInfo") or {}).get("promotions")
                    or (data.get("store") or {}).get("promotions")
                    or []
                )
                for promo in promo_lists:
                    if not isinstance(promo, dict):
                        continue
                    desc = (
                        promo.get("title")
                        or promo.get("description")
                        or promo.get("text")
                        or ""
                    )
                    if not desc or desc in seen:
                        continue
                    seen.add(desc)
                    promotions.append(PromotionInfo(
                        type=promo.get("type") or "promotion",
                        description=desc,
                        value=self._extract_promo_value(desc),
                        conditions=promo.get("conditions") or "",
                    ))
            except Exception as e:
                self.logger.debug(f"_promotions_from_api error: {e}")
                continue

        return promotions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_promo_value(self, text: str) -> str:
        """Extract a promo value like '50%', '$30', '2x1' from text."""
        for pat in [r'\d+%', r'\$\s*\d+', r'2x1', r'3x2']:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""
