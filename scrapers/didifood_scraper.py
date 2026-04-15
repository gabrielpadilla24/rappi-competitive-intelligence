"""
DiDi Food scraper implementation.

Scrapes restaurant data from www.didi-food.com using Playwright with
localStorage-based session authentication and pl= URL parameter for location.

Authentication:
  DiDi Food stores the session in localStorage (isLogin, ticket, uid, etc.).
  The scraper injects these values via page.evaluate() on the domain root
  before navigating to the feed.  Basic locale/region cookies are also set
  via context.add_cookies().

  If the session has expired the scraper logs a clear warning:
    "Session expired — need fresh cookies"
  Update _LS_TICKET and _LS_UID below with fresh values when that happens.

Location:
  Delivery coordinates are encoded as a base64 JSON string in the `pl=`
  URL parameter, using the same approach as Uber Eats Mexico.

Price format:
  DiDi Food displays prices as "MX$67.00" or "$67" — both are parsed.
"""

import re
import json
import base64
import random
import asyncio
from typing import Optional

# ── Session-expiry signals ────────────────────────────────────────────────────
# If the browser is redirected to one of these URL patterns OR finds these
# strings in the page body, the injected cookies have expired.
_LOGIN_URL_PATTERNS = ("/login", "/sign-in", "/auth", "/signin")

_SESSION_EXPIRED_TEXT = (
    "iniciar sesión",
    "inicia sesión",
    "sign in to continue",
    "tu sesión ha expirado",
    "session expired",
    "please log in",
)

# ── Bot-block signals ─────────────────────────────────────────────────────────
_BLOCK_SIGNALS = (
    "you have been blocked",
    "access denied",
    "cf-browser-verification",
    "ddos-guard",
    "ray id:",
)

# ── API URL keywords ──────────────────────────────────────────────────────────
# Responses from these endpoints carry menu / store data worth intercepting.
_API_URL_KEYWORDS = (
    "/store/", "/menu/", "/product/", "/catalog/",
    "didi-food.com/api", "/restaurant/",
    "/v1/", "/v2/", "/v3/",
    "food/api",
)

# ── Sub-category keywords ─────────────────────────────────────────────────────
_SUBCATEGORY_KEYWORDS = frozenset({
    "postres", "desayunos", "helados", "bebidas", "café", "cafe",
    "pollos", "ensaladas", "snacks", "malteadas", "mccafé", "mccafe",
    "pollos de", "postres de", "desayunos de",
})

# ── localStorage session values ───────────────────────────────────────────────
# DiDi Food stores the session in localStorage, not in cookies.
# Update _LS_TICKET and _LS_UID when "Session expired — need fresh cookies"
# appears in the log.  Run `python test_didifood_quick.py` to verify.
_LS_TICKET = (
    "XOISX2w17pOwH6qedRjImSVDbP0l65nT164G3vU6-V8kzE1KBDEQgNG7fFuLoX6"
    "SVFJbD-Ad1FFwEUFx1fTdpZn1g3ewlSJuelOEbZQJ2ylznTGFHdTMNcxb9qFLL2-"
    "UZY5pzUYKu1M8vyC8UjFWi-HePK0PE94pF-7Uwe_338_bnUpVtVP4eDyuK67nk-"
    "KpZ1hMn7naQvii_PwPAAD__w=="
)
_LS_UID = "369436224271561"

# ── Basic locale/region cookies ───────────────────────────────────────────────
# These are set via context.add_cookies() so they survive across navigations.
# The app may check both cookies and localStorage for locale/region.
_BASIC_COOKIES = [
    {"name": "locale",          "value": "es-MX",   "domain": ".didi-food.com", "path": "/"},
    {"name": "country",         "value": "Mexico",  "domain": ".didi-food.com", "path": "/"},
    {"name": "i18n_redirected", "value": "es-419",  "domain": ".didi-food.com", "path": "/"},
    {
        "name": "cto_bundle",
        "value": (
            "_zkAx19VNVFHQk8lMkJUWFQlMkJVOUZiS0JhVjZaY1c5UzlWQWJEUVp5NkJZcklwUmZqRVRGVTdhQnRR"
            "NUdHUFhMelNUTElrSiUyQkd1TUtsSWxSTXR3N3AzY2RRUzdNdWNQSUhQQVBLNHJvUGoyRFl6MDdFNVBm"
            "aFI1N1NTTWVkQjU3U0FReEwxUWYyUSUyRjBsWGtJWFZOUElFNDZHaGxTQSUzRCUzRA=="
        ),
        "domain": ".didi-food.com",
        "path": "/",
    },
]


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
from scrapers.utils.parsers import parse_price, parse_time_range, fuzzy_match
from config.locations import Location
from config.products import Product, TargetRestaurant
from config.settings import (
    PLATFORM_URLS,
    PAGE_LOAD_TIMEOUT,
)


class DididfoodScraper(BaseScraper):
    """Scraper for DiDi Food Mexico (www.didi-food.com)."""

    def __init__(self):
        super().__init__(platform_name="didifood")
        self._playwright = None
        self._api_responses: list[dict] = []
        self._current_restaurant_url: Optional[str] = None
        self._restaurant_search_count = 0
        self._pl_param: Optional[str] = None  # base64 location param, set in set_location

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """
        Initialize browser, inject session into localStorage, enable API interception.

        DiDi Food stores auth state in localStorage (isLogin, ticket, uid …),
        not in cookies.  The injection sequence is:
          1. Inject basic locale/region cookies (survive all navigations).
          2. Navigate to the domain root so localStorage is scoped correctly.
          3. Set all required localStorage keys via page.evaluate().
          4. Reload the page so the React app reads the injected session.
        """
        from playwright.async_api import async_playwright
        self.logger.info("Starting DiDi Food browser")
        self._playwright = await async_playwright().start()
        self.browser, self.context, self.page = await setup_stealth_browser(
            self._playwright
        )

        # Step 1 — basic locale/region cookies (set before any navigation)
        await self.context.add_cookies(_BASIC_COOKIES)
        self.logger.info(f"Injected {len(_BASIC_COOKIES)} basic cookies")

        # Step 2 — navigate to domain root so localStorage is on the correct origin
        self.logger.info("Navigating to domain root for localStorage injection")
        await self.page.goto(
            "https://www.didi-food.com/es-MX",
            timeout=PAGE_LOAD_TIMEOUT,
            wait_until="domcontentloaded",
        )

        # Step 3 — inject session into localStorage
        await self.page.evaluate(f"""() => {{
            localStorage.setItem('isLogin', 'true');
            localStorage.setItem('ticket', '"{_LS_TICKET}"');
            localStorage.setItem('uid', '"{_LS_UID}"');
            localStorage.setItem('poiCityId', '52090100');
            localStorage.setItem('countryCode', '"MX"');
            localStorage.setItem('finalLocale', '"es-MX"');
            localStorage.setItem('locale', 'es-MX');
            localStorage.setItem('country', 'Mexico');
        }}""")
        self.logger.info("localStorage session injected")

        # Step 4 — reload so the React app picks up the injected session
        await self.page.reload(wait_until="domcontentloaded")
        await random_delay(2, 3)
        self.logger.info("Page reloaded — session should be active")

        # Capture API responses — menu and store data arrive via XHR/fetch.
        self.page.on("response", self._capture_api_response)
        self.logger.info("DiDi Food browser ready")

    async def teardown(self) -> None:
        """Close browser and release Playwright resources."""
        for attr, label in [
            ("page",        "page"),
            ("context",     "context"),
            ("browser",     "browser"),
            ("_playwright", "playwright"),
        ]:
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                await obj.close() if attr != "_playwright" else await obj.stop()
            except Exception as e:
                self.logger.warning(f"Error closing {label}: {e}")
        self.logger.info("DiDi Food browser closed")

    # ------------------------------------------------------------------
    # API interception
    # ------------------------------------------------------------------

    async def _capture_api_response(self, response) -> None:
        """Background handler: capture JSON from DiDi Food's internal API."""
        url = response.url
        if not any(kw in url for kw in _API_URL_KEYWORDS):
            return
        if response.status != 200:
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        try:
            body = await response.json()
            self._api_responses.append({"url": url, "data": body})
            self.logger.debug(f"Captured API response: {url[:100]}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Anti-detection helpers
    # ------------------------------------------------------------------

    def _gauss_secs(self, mean: float, sigma: float, lo: float, hi: float) -> float:
        """Sample a Gaussian delay clamped to [lo, hi] seconds."""
        return max(lo, min(hi, random.gauss(mean, sigma)))

    async def _gauss_delay(self, mean: float, sigma: float, lo: float, hi: float) -> None:
        secs = self._gauss_secs(mean, sigma, lo, hi)
        self.logger.debug(f"Gauss delay: {secs:.1f}s (μ={mean})")
        await asyncio.sleep(secs)

    def _is_subcategory_card(self, text: str) -> bool:
        text_lower = text.lower()
        return any(
            re.search(r'\b' + re.escape(kw) + r'\b', text_lower)
            for kw in _SUBCATEGORY_KEYWORDS
        )

    # ------------------------------------------------------------------
    # Session / block detection
    # ------------------------------------------------------------------

    async def _is_session_expired(self, page_text: str, url: str) -> bool:
        """
        Return True and log a clear warning if the localStorage session has expired.

        Checks three signals in priority order:
          1. URL redirect to a login page.
          2. localStorage isLogin != "true" (most reliable for DiDi Food).
          3. Page text contains a login prompt.

        The log message "Session expired — need fresh cookies" is the cue to
        update _LS_TICKET and _LS_UID in this file.
        """
        # 1. URL-based redirect check
        url_lower = url.lower()
        for pat in _LOGIN_URL_PATTERNS:
            if pat in url_lower:
                self.logger.warning(
                    f"Session expired — need fresh cookies "
                    f"(redirected to login URL: {url})"
                )
                return True

        # 2. localStorage check — DiDi Food sets isLogin="true" when authenticated
        try:
            is_logged = await self.page.evaluate(
                "() => localStorage.getItem('isLogin')"
            )
            if is_logged != "true":
                self.logger.warning(
                    f"Session expired — need fresh cookies "
                    f"(localStorage isLogin={is_logged!r}, expected 'true')"
                )
                return True
        except Exception as e:
            self.logger.debug(f"localStorage check failed (non-critical): {e}")

        # 3. Page-text check
        text_lower = page_text.lower()
        for signal in _SESSION_EXPIRED_TEXT:
            if signal in text_lower:
                self.logger.warning(
                    f"Session expired — need fresh cookies "
                    f"(page text matched: {signal!r})"
                )
                return True

        return False

    def _is_blocked(self, page_text: str, url: str = "") -> bool:
        text_lower = page_text.lower()
        for signal in _BLOCK_SIGNALS:
            if signal in text_lower:
                self.logger.warning(f"Block signal matched: {signal!r}")
                return True
        if "/cdn-cgi/" in url:
            self.logger.warning(f"Block signal matched: Cloudflare URL in {url!r}")
            return True
        return False

    def _feed_has_restaurants(self, page_text: str, url: str) -> bool:
        """Return True if the page looks like a restaurant feed (not login/empty)."""
        text_lower = page_text.lower()
        has_content = any(
            kw in text_lower
            for kw in ("restaurante", "restaurant", "tienda", "menú", "menu")
        )
        is_login = any(pat in url.lower() for pat in _LOGIN_URL_PATTERNS)
        return has_content and not is_login

    # ------------------------------------------------------------------
    # set_location
    # ------------------------------------------------------------------

    def _encode_pl_param(self, location: Location) -> str:
        """
        Encode delivery coordinates as a base64 JSON string for the `pl=` URL
        parameter.  Uses the same structure as Uber Eats Mexico.
        """
        city_name = (
            "Ciudad de México"
            if location.city in ("CDMX", "Ciudad de México")
            else location.city
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
        return base64.urlsafe_b64encode(
            json.dumps(pl_data, separators=(",", ":")).encode()
        ).decode()

    async def set_location(self, location: Location) -> bool:
        """
        Navigate to DiDi Food and set the delivery location.

        Approach 1 (preferred): Navigate directly to the feed with ?pl=<encoded>.
          This skips any address modal entirely.
        Approach 2 (fallback): Navigate to base, fill the address input.
        Approach 3 (last resort): Use browser geolocation only.
        """
        try:
            await self.context.grant_permissions(["geolocation"])
            await self.context.set_geolocation(
                {"latitude": location.lat, "longitude": location.lng}
            )
            self.logger.info(
                f"Geolocation set: ({location.lat}, {location.lng}) for {location.short_name}"
            )

            self._api_responses.clear()
            pl_param = self._encode_pl_param(location)
            self._pl_param = pl_param

            # ── Approach 1: pl= encoded URL ──────────────────────────────
            feed_url = PLATFORM_URLS["didifood"]["feed"]
            pl_url = f"{feed_url}?pl={pl_param}"
            self.logger.info(f"Navigating with pl= URL: {pl_url[:120]}…")
            await self.page.goto(pl_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="load")
            await self._gauss_delay(3, 0.8, 2, 5)

            page_text = await self.page.text_content("body") or ""
            current_url = self.page.url
            self.logger.info(f"Landed on: {current_url}")

            if await self._is_session_expired(page_text, current_url):
                return False
            if self._is_blocked(page_text, current_url):
                self.logger.warning("DiDi Food page is blocked — cannot set location")
                return False
            if self._feed_has_restaurants(page_text, current_url):
                self.logger.info(f"Location set via pl= URL: {location.short_name}")
                return True

            # ── Approach 2: address input ─────────────────────────────────
            self.logger.info("pl= URL did not yield restaurant feed — trying address input")
            base_url = PLATFORM_URLS["didifood"]["base"]
            await self.page.goto(base_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            await self._gauss_delay(3, 1, 2, 5)

            page_text = await self.page.text_content("body") or ""
            if await self._is_session_expired(page_text, self.page.url):
                return False

            address_set = await self._fill_address_input(location.address)
            if address_set:
                self.logger.info(f"Location set via address input: {location.short_name}")
                return True

            # ── Approach 3: geolocation only ──────────────────────────────
            self.logger.warning(
                "Could not set address via UI — relying on browser geolocation"
            )
            page_text = await self.page.text_content("body") or ""
            if await self._is_session_expired(page_text, self.page.url):
                return False
            if self._feed_has_restaurants(page_text, self.page.url):
                self.logger.info("Page has restaurant content — using geolocation fallback")
                return True
            return False

        except Exception as e:
            self.logger.error(f"set_location failed: {e}")
            return False

    async def _fill_address_input(self, address: str) -> bool:
        """Type address into the DiDi Food autocomplete input and confirm."""
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

            suggestion_selectors = [
                '[role="option"]',
                '[role="listbox"] li',
                'ul[role="listbox"] li',
                'li[class*="suggestion"]',
                'div[class*="suggestion"]',
                'div[class*="autocomplete"] li',
            ]
            suggestion_el = None
            for sel in suggestion_selectors:
                try:
                    suggestion_el = await self.page.wait_for_selector(sel, timeout=4000)
                    if suggestion_el:
                        break
                except Exception:
                    continue

            if suggestion_el:
                await suggestion_el.click()
                await random_delay(2, 3)
            else:
                for sel in [
                    'button:has-text("Buscar comida")',
                    'button:has-text("Buscar")',
                    'button[type="submit"]',
                ]:
                    try:
                        btn = await self.page.wait_for_selector(sel, timeout=2000)
                        if btn:
                            await btn.click()
                            break
                    except Exception:
                        continue
                else:
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
        """Search for a restaurant on DiDi Food and navigate to its store page."""
        try:
            self._restaurant_search_count += 1
            self._api_responses.clear()

            # From the 2nd restaurant onward, add an anti-bot delay and return to
            # the feed with the pl= param so location context is preserved.
            if self._restaurant_search_count > 1:
                self.logger.info(
                    f"Extended anti-bot delay before restaurant "
                    f"#{self._restaurant_search_count} ({restaurant.name})"
                )
                await self._gauss_delay(10, 2, 7, 15)
                feed_url = PLATFORM_URLS["didifood"]["feed"]
                if self._pl_param:
                    feed_url = f"{feed_url}?pl={self._pl_param}"
                await self.page.goto(feed_url, timeout=PAGE_LOAD_TIMEOUT, wait_until="load")
                await self._gauss_delay(3, 0.8, 2, 5)

                page_text = await self.page.text_content("body") or ""
                if await self._is_session_expired(page_text, self.page.url):
                    self.logger.error(
                        "Session expired during restaurant search — aborting"
                    )
                    return None

            # Try search bar first
            result = await self._search_via_search_bar(restaurant)
            if result:
                return result

            # Fallback: scan current page for restaurant cards
            self.logger.info(
                "Search bar approach failed — scanning page for restaurant cards"
            )
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
            try:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await simulate_human_scroll(self.page, scrolls=1)

            return await self._find_restaurant_on_page(restaurant)

        except Exception as e:
            self.logger.debug(f"Search bar error: {e}")
            return None

    async def _find_restaurant_on_page(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Scan the current page for a matching restaurant card and navigate to it."""
        card_selectors = [
            'a[href*="/store/"]',
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

        # Wait up to 10 s for at least one card type to appear before scanning.
        for selector in card_selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=10000)
                break
            except Exception:
                continue

        for selector in card_selectors:
            try:
                cards = await self.page.query_selector_all(selector)
                if not cards:
                    continue

                all_texts = []
                for card in cards:
                    t = (await card.text_content() or "").strip()
                    if t:
                        all_texts.append(t[:60])
                self.logger.debug(
                    f"Selector '{selector}' found {len(cards)} cards: {all_texts}"
                )

                matches: list[tuple[str, object]] = []
                for card in cards:
                    text = await card.text_content() or ""
                    if fuzzy_match(restaurant.search_terms, text):
                        matches.append((text.strip(), card))

                if not matches:
                    continue

                # Non-subcategory first, then shortest name (most exact match).
                matches.sort(key=lambda x: (self._is_subcategory_card(x[0]), len(x[0])))
                best_text, best_card = matches[0]

                if len(matches) > 1:
                    skipped = [t[:40] for t, _ in matches[1:]]
                    self.logger.debug(f"Skipped lower-ranked cards: {skipped}")

                if self._is_subcategory_card(best_text):
                    self.logger.warning(
                        f"Best DiDi match '{best_text[:60]}' looks like a sub-category "
                        f"store. Proceeding anyway — product matches may fail."
                    )
                else:
                    self.logger.info(f"Matched DiDi Food card: {best_text[:60]}")

                href = await best_card.get_attribute("href") or ""
                if href:
                    if href.startswith("/"):
                        href = f"https://www.didi-food.com{href}"
                    # Append pl= param so the store page uses the correct location.
                    if self._pl_param and "pl=" not in href:
                        sep = "&" if "?" in href else "?"
                        href = f"{href}{sep}pl={self._pl_param}"
                    self._current_restaurant_url = href
                    await self.page.goto(href, timeout=PAGE_LOAD_TIMEOUT, wait_until="load")
                else:
                    await best_card.click()

                await self._gauss_delay(2, 0.5, 1.5, 4)

                page_text = await self.page.text_content("body") or ""
                if await self._is_session_expired(page_text, self.page.url):
                    self.logger.error(
                        "Session expired after navigating to restaurant — aborting"
                    )
                    return None

                return await self._extract_restaurant_info(restaurant)

            except Exception as e:
                self.logger.debug(f"Card selector '{selector}' error: {e}")
                continue

        self.logger.warning(f"Restaurant '{restaurant.name}' not found on DiDi Food")
        return None

    async def _extract_restaurant_info(
        self, restaurant: TargetRestaurant
    ) -> Optional[RestaurantResult]:
        """Extract name, rating, review count from the restaurant store page."""
        try:
            name = restaurant.name
            rating = None
            review_count = None

            for sel in [
                'h1',
                '[data-testid*="store-name"]',
                '[class*="store-name"]',
                '[class*="restaurant-name"]',
                '[class*="shop-name"]',
            ]:
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

            # Rating: "X.X" near a star glyph or opening parenthesis
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
                    review_count = int(review_match.group(1).replace(",", ""))
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
            # Try structured API data first
            api_delivery = self._delivery_from_api()
            if api_delivery:
                return api_delivery

            delivery_info = DeliveryInfo()
            page_text = await self.page.text_content("body") or ""

            # ── Delivery fee ─────────────────────────────────────────────
            if re.search(
                r'(?:env[íi]o|delivery|costo\s+de\s+env[íi]o)\s*(?:gratis|free)',
                page_text, re.IGNORECASE,
            ):
                delivery_info.fee_mxn = 0.0
            else:
                fee_patterns = [
                    # DiDi Food native format: "MX$29.00 envío"
                    r'MX\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:de\s+)?env[íi]o',
                    r'env[íi]o.{0,40}?MX\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    # Standard "$" format
                    r'env[íi]o\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:de\s+)?env[íi]o',
                    r'env[íi]o.{0,80}?\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                ]
                for pattern in fee_patterns:
                    m = re.search(pattern, page_text, re.IGNORECASE | re.DOTALL)
                    if m:
                        price = parse_price(m.group(1))
                        if price is not None and price <= 80:
                            delivery_info.fee_mxn = price
                        elif price is not None:
                            self.logger.warning(
                                f"Discarding implausible delivery fee ${price} (max $80)"
                            )
                        break

            # ── Delivery time ─────────────────────────────────────────────
            time_min, time_max = parse_time_range(page_text)
            delivery_info.estimated_time_min = time_min
            delivery_info.estimated_time_max = time_max

            # ── Service fee ───────────────────────────────────────────────
            for pat in [
                r'MX\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:tarifa\s+de\s+)?servicio',
                r'servicio\s*[:\s•·]\s*MX\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                r'servicio\s*[:\s•·]\s*\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
            ]:
                m = re.search(pat, page_text, re.IGNORECASE)
                if m:
                    delivery_info.service_fee_mxn = parse_price(m.group(1))
                    break

            self.logger.info(
                f"DiDi delivery info: fee={delivery_info.fee_mxn}, "
                f"time={delivery_info.estimated_time_min}-"
                f"{delivery_info.estimated_time_max} min"
            )

            if delivery_info.fee_mxn is None and delivery_info.estimated_time_min is None:
                self.logger.warning("Could not extract any delivery info from DiDi Food")
                return None

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
                    or (data.get("data") or {}).get("store")
                    or (data.get("data") or {}).get("restaurant")
                )
                if not store:
                    continue
                fee = (
                    store.get("deliveryFee")
                    or store.get("delivery_fee")
                    or store.get("shippingFee")
                )
                time_min = (
                    store.get("minDeliveryTime")
                    or store.get("min_delivery_time")
                    or store.get("timeMin")
                )
                time_max = (
                    store.get("maxDeliveryTime")
                    or store.get("max_delivery_time")
                    or store.get("timeMax")
                )
                if fee is not None or time_min is not None:
                    # Fees >500 are likely in cents (e.g. 2900 = MX$29.00)
                    fee_mxn = (
                        float(fee) / 100
                        if fee and float(fee) > 500
                        else (float(fee) if fee is not None else None)
                    )
                    return DeliveryInfo(
                        fee_mxn=fee_mxn,
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
        """Search for a product in the DiDi Food restaurant menu."""
        try:
            # API data first (most reliable — avoids DOM fragility)
            api_result = self._product_from_api(product)
            if api_result:
                return api_result

            await simulate_human_scroll(self.page, scrolls=3)

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

            # Collect ALL fuzzy matches across all selectors, then return the
            # shortest name.  This prevents combos like "Combo Big Mac Mediano"
            # from winning over "Big Mac".
            dom_matches: list[tuple[str, Optional[float]]] = []
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
                        price = self._extract_price_from_element(item_text)
                        item_name = (
                            item_text.split("\n")[0].strip()
                            if "\n" in item_text
                            else item_text[:60].strip()
                        )
                        dom_matches.append((item_name, price))
                    except Exception as e:
                        self.logger.debug(f"Item parse error: {e}")
                        continue
                if dom_matches:
                    break  # found matches with this selector; don't try others

            if dom_matches:
                dom_matches.sort(key=lambda x: len(x[0]))
                best_name, best_price = dom_matches[0]
                if len(dom_matches) > 1:
                    skipped = [f"'{n}'" for n, _ in dom_matches[1:3]]
                    self.logger.debug(f"Shortest DOM match wins; skipped: {skipped}")
                self.logger.info(f"DiDi product match: '{best_name}' → ${best_price}")
                return ProductResult(
                    name=product.name,
                    reference_id=product.id,
                    price_mxn=best_price,
                    available=best_price is not None,
                    original_name=best_name,
                )

            # Last resort: page text scan
            self.logger.debug(
                f"No DOM match for '{product.name}' — scanning page text"
            )
            return await self._product_from_page_text(product)

        except Exception as e:
            self.logger.error(f"get_product_price failed: {e}")
            return None

    def _product_from_api(self, product: Product) -> Optional[ProductResult]:
        """
        Try to find product price in captured API responses.
        Collects all matches across all responses, returns the shortest name.
        """
        api_matches: list[tuple[str, Optional[float]]] = []
        for resp in self._api_responses:
            try:
                data = resp.get("data", {})
                items = (
                    data.get("products")
                    or data.get("items")
                    or data.get("menuItems")
                    or (data.get("data") or {}).get("products")
                    or (data.get("data") or {}).get("items")
                    or []
                )
                if not isinstance(items, list):
                    continue
                for item in items:
                    name = item.get("name", "") or item.get("title", "")
                    if not fuzzy_match(product.search_terms, name):
                        continue
                    raw = item.get("price") or item.get("basePrice") or item.get("salePrice")
                    if raw is not None:
                        price: Optional[float] = (
                            float(raw) / 100 if float(raw) > 500 else float(raw)
                        )
                    else:
                        price = None
                    api_matches.append((name, price))
            except Exception:
                continue

        if not api_matches:
            return None

        api_matches.sort(key=lambda x: len(x[0]))
        best_name, best_price = api_matches[0]
        if len(api_matches) > 1:
            skipped = [f"'{n}'" for n, _ in api_matches[1:3]]
            self.logger.debug(f"API: shortest match wins; skipped: {skipped}")
        self.logger.info(f"DiDi product via API: '{best_name}' → ${best_price}")
        return ProductResult(
            name=product.name,
            reference_id=product.id,
            price_mxn=best_price,
            available=True,
            original_name=best_name,
        )

    def _extract_price_from_element(self, text: str) -> Optional[float]:
        """Extract the first valid price. Handles MX$, $, and MXN formats."""
        # DiDi Food native format: MX$67.00
        m = re.search(r'MX\$\s*(\d[\d,]*(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if m:
            return parse_price(m.group(1))
        # Dollar sign
        m = re.search(r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)', text)
        if m:
            return parse_price(m.group(1))
        # MXN prefix
        m = re.search(r'MXN\s*(\d[\d,]*(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if m:
            return parse_price(m.group(1))
        return None

    async def _product_from_page_text(self, product: Product) -> Optional[ProductResult]:
        """Last resort: scan full page text for product name + price."""
        try:
            page_text = await self.page.text_content("body") or ""
            for term in product.search_terms:
                for pattern in [
                    re.escape(term) + r'.{0,80}?MX\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                    re.escape(term) + r'.{0,80}?\$\s*(\d[\d,]*(?:\.\d{1,2})?)',
                ]:
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
                                type=(
                                    "discount"
                                    if "%" in text or "off" in text.lower()
                                    else "promotion"
                                ),
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
        for pat in [r'\d+%', r'MX\$\s*\d+', r'\$\s*\d+', r'2x1', r'3x2']:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(0)
        return ""
