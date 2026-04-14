"""
Quick smoke-test for the Uber Eats scraper.
Runs with headless=False so you can watch the browser.
Usage: python test_ubereats_quick.py
"""

import os
import asyncio
import logging

# ── Patch HEADLESS before any scraper code imports the setting ──────────────
import scrapers.utils.anti_detection as _ad
_ad.HEADLESS = False
# ── Short block-wait during manual testing (default is 2–5 min) ─────────────
os.environ.setdefault("UBEREATS_BLOCK_WAIT_SECS", "10")
# ────────────────────────────────────────────────────────────────────────────

from scrapers.ubereats_scraper import UberEatsScraper
from config.locations import get_location_by_id
from config.products import PRIORITY_RESTAURANTS, get_products_by_restaurant

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_ubereats")


async def test():
    location = get_location_by_id("polanco")
    restaurant = PRIORITY_RESTAURANTS[0]  # McDonald's
    products = get_products_by_restaurant(restaurant.id)

    logger.info(f"Location  : {location.short_name} ({location.lat}, {location.lng})")
    logger.info(f"Restaurant: {restaurant.name}")
    logger.info(f"Products  : {[p.name for p in products]}")

    scraper = UberEatsScraper()
    await scraper.setup()

    try:
        result = await scraper.scrape_restaurant_at_location(location, restaurant, products)
    finally:
        await scraper.teardown()

    print("\n" + "=" * 60)
    print("RESULT SUMMARY")
    print("=" * 60)
    print(f"Completeness : {result.data_completeness}")
    print(f"Duration     : {result.scrape_duration_seconds}s")
    print(f"Restaurant   : {result.restaurant}")
    print(f"Delivery     : {result.delivery}")
    print(f"Products ({len(result.products)}):")
    for p in result.products:
        status = f"${p.price_mxn}" if p.price_mxn else "NOT FOUND"
        print(f"  {p.name:<30} {status}  (original_name={p.original_name!r})")
    print(f"Promotions ({len(result.promotions)}):")
    for promo in result.promotions:
        print(f"  [{promo.type}] {promo.description!r}  value={promo.value!r}")
    print(f"Errors ({len(result.errors)}):")
    for err in result.errors:
        print(f"  - {err}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    asyncio.run(test())
