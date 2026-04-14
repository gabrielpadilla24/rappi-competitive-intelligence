"""
Quick smoke test for the DiDi Food scraper.
Tests 1 location (Polanco) × 1 restaurant (McDonald's).
Runs headless=False so you can see what the browser does.

If you see "Session expired — need fresh cookies" in the output,
update the token and ttcsid values in scrapers/didifood_scraper.py.

Usage: python test_didifood_quick.py
"""

import asyncio
import logging

# ── Patches (must happen before scraper imports) ─────────────────────────────
import scrapers.utils.anti_detection as _ad
_ad.HEADLESS = False
# ─────────────────────────────────────────────────────────────────────────────

from scrapers.didifood_scraper import DididfoodScraper
from scrapers.base import ScrapeResult
from config.locations import get_location_by_id
from config.products import TARGET_RESTAURANTS, get_products_by_restaurant

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)
logger = logging.getLogger("didifood_quick_test")


def _fmt_price(price) -> str:
    return f"${price:.2f}" if price is not None else "—"


def _print_result(result: ScrapeResult) -> None:
    icon = {"full": "✅", "partial": "⚠️ ", "failed": "❌"}.get(result.data_completeness, "?")
    rest_name = result.restaurant.name if result.restaurant else "?"

    print(f"\n{'═'*60}")
    print(f"  {icon}  DiDi Food — {result.location_id}  ×  {rest_name}")
    print(f"  Completeness : {result.data_completeness}")
    print(f"  Duration     : {result.scrape_duration_seconds}s")
    print(f"{'─'*60}")
    if result.restaurant:
        print(f"  Restaurant   : {result.restaurant.name}")
        print(f"  Rating       : {result.restaurant.rating}   Reviews: {result.restaurant.review_count}")
    if result.delivery:
        print(f"  Delivery fee : {_fmt_price(result.delivery.fee_mxn)}")
        print(
            f"  ETA          : {result.delivery.estimated_time_min}–"
            f"{result.delivery.estimated_time_max} min"
        )
    print(f"{'─'*60}")
    for p in result.products:
        avail = _fmt_price(p.price_mxn) if p.available else "NOT FOUND"
        orig  = f"  ← '{p.original_name}'" if p.original_name and p.original_name != p.name else ""
        print(f"  {p.name:<35} {avail}{orig}")
    if result.promotions:
        vals = ", ".join(pr.value or pr.description[:20] for pr in result.promotions[:4])
        print(f"  Promos       : {vals}")
    if result.errors:
        print(f"  Errors       : {'; '.join(result.errors)}")
    print(f"{'═'*60}\n")


async def main():
    location   = get_location_by_id("polanco")
    restaurant = next(r for r in TARGET_RESTAURANTS if r.id == "mcdonalds")
    products   = get_products_by_restaurant(restaurant.id)

    logger.info(f"Quick test: {location.short_name} × {restaurant.name}")
    logger.info(f"Products  : {[p.name for p in products]}")

    scraper = DididfoodScraper()
    await scraper.setup()
    try:
        result = await scraper.scrape_restaurant_at_location(location, restaurant, products)
    finally:
        await scraper.teardown()

    _print_result(result)


if __name__ == "__main__":
    asyncio.run(main())
