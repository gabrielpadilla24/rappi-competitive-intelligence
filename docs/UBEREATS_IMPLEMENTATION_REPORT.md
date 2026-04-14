# Uber Eats Scraper — Implementation Report

## 1. Project Structure

```
rappi-competitive-intelligence/
├── scrapers/
│   ├── base.py                  — Abstract base class + all data models
│   ├── rappi_scraper.py         — Fully implemented Rappi scraper (reference)
│   ├── ubereats_scraper.py      — Uber Eats scraper (this implementation)
│   ├── didifood_scraper.py      — DiDi Food scraper (partial)
│   └── utils/
│       ├── anti_detection.py    — Stealth browser setup, delays, scroll, mouse
│       ├── retry.py             — Async retry with exponential backoff
│       └── parsers.py           — parse_price, parse_time_range, fuzzy_match
├── config/
│   ├── settings.py              — Global constants (timeouts, delays, URLs, UAs)
│   ├── locations.py             — 25 Location objects (CDMX + 2 secondary cities)
│   └── products.py              — Product + TargetRestaurant models + constants
├── run_scraper.py               — CLI entry point / orchestration loop
├── scripts/
│   ├── generate_sample_data.py  — Generates synthetic test data
│   └── consolidate_data.py      — Converts raw JSON to CSV
├── analysis/                    — Comparison charts and insights
├── dashboard/                   — Streamlit dashboard
├── data/
│   ├── raw/                     — Per-scrape JSON files
│   ├── processed/               — Consolidated CSVs
│   └── screenshots/             — Browser screenshots
└── tests/                       — Integration and unit tests
```

---

## 2. BaseScraper — Interface & Data Models

### Data Models (`scrapers/base.py`)

```python
@dataclass
class ProductResult:
    name: str               # Canonical product name (from config)
    reference_id: str       # Product ID (from config)
    price_mxn: Optional[float] = None
    available: bool = True
    description: str = ""
    original_name: str = ""  # Actual name shown on the platform

@dataclass
class DeliveryInfo:
    fee_mxn: Optional[float] = None
    service_fee_mxn: Optional[float] = None
    estimated_time_min: Optional[int] = None
    estimated_time_max: Optional[int] = None
    free_delivery_threshold_mxn: Optional[float] = None
    surge_active: bool = False

@dataclass
class PromotionInfo:
    type: str = ""           # discount | free_delivery | bundle | cashback
    description: str = ""
    value: str = ""          # "50%", "$30 off", "2x1"
    conditions: str = ""

@dataclass
class RestaurantResult:
    name: str
    platform_id: str = ""   # URL used as platform-specific ID
    available: bool = True
    rating: Optional[float] = None
    review_count: Optional[int] = None

@dataclass
class ScrapeResult:
    # Auto-generated
    scrape_id: str          # UUID
    timestamp: str          # ISO 8601 UTC
    # Location metadata
    platform: str
    location_id: str
    location_address: str
    location_lat: float
    location_lng: float
    zone_type: str
    zone_label: str
    city: str
    # Scraped data
    restaurant: Optional[RestaurantResult]
    products: list[ProductResult]
    delivery: Optional[DeliveryInfo]
    promotions: list[PromotionInfo]
    # Metadata
    screenshot_path: str
    errors: list[str]
    data_completeness: str  # "full" | "partial" | "failed"
    scrape_duration_seconds: float
```

### Abstract Methods (all must be implemented)

| Method | Returns | Description |
|--------|---------|-------------|
| `setup()` | None | Initialize browser |
| `teardown()` | None | Close browser |
| `set_location(location)` | bool | Set delivery address |
| `search_restaurant(restaurant)` | Optional[RestaurantResult] | Navigate to restaurant |
| `get_delivery_info()` | Optional[DeliveryInfo] | Extract fees + ETA |
| `get_product_price(product)` | Optional[ProductResult] | Find product price in menu |
| `get_promotions()` | list[PromotionInfo] | Extract visible promotions |

### Orchestration: `scrape_restaurant_at_location()`

This is the single entry point called by `run_scraper.py`. It:
1. Creates a `ScrapeResult` with location metadata
2. Calls `set_location()` — aborts if fails
3. Calls `search_restaurant()` — marks failed if not found
4. Calls `get_delivery_info()`
5. Calls `get_product_price()` for each product in the list
6. Calls `get_promotions()`
7. Takes screenshot if `TAKE_SCREENSHOTS=True`
8. Sets `data_completeness` based on errors

---

## 3. RappiScraper — Reference Implementation

### Key patterns used in Rappi that inform the Uber Eats approach:

**API Interception (primary data source)**
```python
# In setup():
self.page.on("response", self._capture_api_response)

# Handler captures JSON from URLs containing restaurant/store/menu/catalog keywords
async def _capture_api_response(self, response) -> None:
    url = response.url
    if any(kw in url for kw in ["restaurants", "store", "menu", "search", "catalog", "product"]):
        body = await response.json()
        self._api_responses.append({"url": url, "data": body})
```

**Location Setting**
- Sets geolocation via `context.set_geolocation()` first
- Navigates to base URL
- Finds address modal/input via multiple selector fallbacks
- Types with `keyboard.type(address, delay=90)` for human-like typing
- Waits for autocomplete suggestions (`[role="option"]`)
- Clicks first suggestion

**Restaurant Search**
- Tracks `_restaurant_search_count` — adds 8–12s delay on 2nd+ restaurant
- Tries search bar first, falls back to browsing the feed
- Collects all matching store cards via `fuzzy_match(restaurant.search_terms, text)`
- Sorts by `(is_subcategory, name_length)` to prefer the main branch
- Navigates to the best match's URL

**Product Extraction**
- Tries API responses first (`_product_from_api`)
- Scrolls the page with `simulate_human_scroll`
- Tries DOM selectors `[data-qa*="product-item"]`
- Falls back to full-page regex

**Delivery Extraction**
- Tries API responses first (`_delivery_from_api`)
- Regexes on page text for delivery/envío keywords + `$` + amount
- Regexes for time ranges (`\d+–\d+ min`)

---

## 4. Config — Locations

**Location model fields:** `id`, `address`, `colonia`, `alcaldia`, `city`, `lat`, `lng`, `zone_type`, `zone_label`, `priority`, `short_name` (property)

**25 locations breakdown:**
- 5 HIGH INCOME: Polanco, Santa Fe, Condesa, Roma Norte, Lomas
- 5 MEDIUM-HIGH: Del Valle, Del Valle Sur, Country Club, Florida, Mixcoac
- 5 MEDIUM: Narvarte, Narvarte Ote, Agrícola Oriental, Letrán Valle, Tacuba
- 5 LOW/PERIPHERAL: Iztapalapa, Tláhuac, GAM, Ecatepec, Satélite
- 3 COMMERCIAL: Reforma, Centro Histórico, Chapultepec
- 2 SECONDARY: Guadalajara, Monterrey

**Helper functions:**
- `get_location_by_id(id)` — fetch single location
- `get_quick_locations()` — priority=1 only (6 locations)
- `get_locations_by_priority(max_priority=2)` — 23 CDMX locations

---

## 5. Config — Products & Restaurants

**Target Restaurants (by priority):**
- Priority 1: McDonald's, Burger King
- Priority 2: OXXO

**Products tracked:**
- McDonald's: Big Mac, Combo Big Mac, McNuggets 10
- Burger King: Whopper, Combo Whopper
- OXXO: Coca-Cola 500ml, Agua Bonafont 1L

**`fuzzy_match(search_terms, target)`** — returns True if any term is a substring of target (case-insensitive)

---

## 6. Config — Key Settings

| Setting | Value |
|---------|-------|
| `PAGE_LOAD_TIMEOUT` | 30,000 ms |
| `ELEMENT_TIMEOUT` | 10,000 ms |
| `MIN_DELAY_SECONDS` | 3 |
| `MAX_DELAY_SECONDS` | 6 |
| `DELAY_BETWEEN_LOCATIONS` | 8 |
| `HEADLESS` | True |
| `VIEWPORT_WIDTH/HEIGHT` | 1366×768 |
| `TAKE_SCREENSHOTS` | True |

**Uber Eats URLs:**
- Base: `https://www.ubereats.com`
- Feed: `https://www.ubereats.com/mx/feed`
- Search: `https://www.ubereats.com/mx/search?q={query}`
- Store: `https://www.ubereats.com/mx/store/{slug}/{id}`

---

## 7. Utils

### `anti_detection.py`
- `setup_stealth_browser(playwright)` — returns `(browser, context, page)` with stealth patches, `es-MX` locale, `America/Mexico_City` timezone, image/font blocking
- `apply_stealth_scripts(context)` — injects JS to mask `navigator.webdriver`, plugins, languages, chrome runtime, permissions
- `random_delay(min, max)` — `asyncio.sleep(random.uniform(min, max))`
- `human_like_delay()` — `asyncio.sleep(random.uniform(0.5, 1.5))`
- `simulate_human_scroll(page, scrolls=3)` — scroll 200–600px with 0.3–0.8s pauses
- `simulate_mouse_movement(page)` — random mouse moves to 2–5 positions

### `parsers.py`
- `parse_price(text)` — parses `$89`, `MXN 89`, `$1,299.00` → float; extracts only the number after `$` to avoid `2 x $109` → 2109 bug
- `parse_time_range(text)` — parses `25–35 min`, `30 min` → `(min, max)`; validates 1–180 min
- `fuzzy_match(search_terms, target)` — substring check (case-insensitive)

### `retry.py`
- `retry_async(func, *args, max_retries=3, backoff_base=5, ...)` — exponential backoff async retry
- `with_retry(...)` — decorator version
- Exception classes: `ScrapingError`, `BlockedError`, `ElementNotFoundError`, `LocationError`

---

## 8. Uber Eats Scraper — Implementation Plan

### Why the existing placeholder needed enhancement

The placeholder at `scrapers/ubereats_scraper.py` had correct structure and DOM-parsing logic, but was missing several critical features that make the difference between getting blocked and successfully scraping:

1. **No API interception** — Uber Eats makes GraphQL/REST calls that return clean JSON. Not capturing these means relying entirely on fragile DOM parsing.
2. **Uniform delays** — `random.uniform()` creates detectable patterns; Gaussian distribution is harder to fingerprint.
3. **No block detection** — Cloudflare blocks silently serve a JS challenge page; without detection we'd parse garbage.
4. **No `pl=` parameter** — Navigating to `?pl=<encoded_location>` sets location without modal interaction, reducing suspicious behavior.
5. **No between-restaurant delays** — Scraping multiple restaurants in sequence without cooldowns is a strong bot signal.

### Implementation approach

**Phase 1 — API interception setup (in `setup()`)**
```python
self.page.on("response", self._capture_api_response)
```
Intercepts responses from URLs containing: `getFeedV1`, `getCatalog`, `getStore`, `getMenu`, `graphql`, `/eats/`, `/menu/`, `/store/`

**Phase 2 — Location setting with `pl=` param (in `set_location()`)**
```python
pl_data = {
    "address": {
        "location": {"latitude": lat, "longitude": lng},
        "city": "Ciudad de México",
        "country": "MX",
        "formattedAddress": address,
    }
}
pl = base64.urlsafe_b64encode(json.dumps(pl_data).encode()).decode()
url = f"https://www.ubereats.com/mx/feed?pl={pl}"
```
Falls back to address modal interaction if `pl=` doesn't work.

**Phase 3 — Restaurant search with delays (in `search_restaurant()`)**
```python
# On 2nd+ restaurant: Gaussian delay 8–15 seconds
if self._restaurant_search_count > 1:
    await asyncio.sleep(random.gauss(10, 2))  # clamped to [8, 15]
```

**Phase 4 — API-first data extraction**
- `get_delivery_info()` → `_delivery_from_api()` → DOM fallback
- `get_product_price()` → `_product_from_api()` → DOM fallback
- `get_promotions()` → `_promotions_from_api()` → DOM fallback

**Phase 5 — Block detection**
```python
def _is_blocked(self, page_text: str) -> bool:
    signals = ["just a moment", "cloudflare", "checking your browser",
               "access denied", "captcha", "you have been blocked"]
    return any(s in page_text.lower() for s in signals)
```
After 3 consecutive blocks → abort with partial data.

### DOM selectors used (as of Q4 2025)

| Element | Selector |
|---------|---------|
| Store card | `a[data-testid="store-card"]`, `[data-testid="store-card"]` |
| Delivery fee | `[data-testid="delivery-fee"]`, `[data-testid="deliveryFee"]`, `[data-testid="store-delivery-fee"]` |
| Menu item | `li[data-testid^="store-item-"]`, `[data-testid^="menu-item"]` |
| Item name/price | `span[data-testid="rich-text"]` |
| Promotion tags | `[data-baseweb="tag"]`, `[data-testid*="promo"]` |
| Restaurant title | `h1`, `[data-testid="store-title"]` |

### Known limitations

1. **Service fee**: Usually only visible in checkout flow, not on restaurant page. Implementation attempts extraction but may often return `None`.
2. **`pl=` reliability**: The exact JSON schema Uber Eats expects for the `pl=` parameter is not publicly documented and may change. The implementation has a fallback.
3. **Menu lazy loading**: Uber Eats loads menu sections as user scrolls. `simulate_human_scroll` helps but may not load all sections.
4. **GraphQL response format**: UberEats GraphQL schema changes frequently. The API parser tries multiple common field names but DOM fallback remains important.
