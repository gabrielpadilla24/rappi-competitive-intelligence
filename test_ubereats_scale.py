"""
Scale test for the Uber Eats scraper.
Runs 3 locations × 2 priority-1 restaurants = 6 scrapes.
Prints a partial summary after each scrape and a consolidated table at the end.

Usage: python test_ubereats_scale.py
"""

import os
import asyncio
import logging
import random
from datetime import datetime

# ── Patches (must happen before scraper imports) ────────────────────────────
import scrapers.utils.anti_detection as _ad
_ad.HEADLESS = False
os.environ.setdefault("UBEREATS_BLOCK_WAIT_SECS", "15")
# ────────────────────────────────────────────────────────────────────────────

from scrapers.ubereats_scraper import UberEatsScraper
from scrapers.base import ScrapeResult
from config.locations import get_location_by_id
from config.products import PRIORITY_RESTAURANTS, get_products_by_restaurant

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Silence debug noise from asyncio / playwright internals
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)
logger = logging.getLogger("scale_test")

# ── Test matrix ─────────────────────────────────────────────────────────────
LOCATION_IDS = ["polanco", "condesa", "roma_norte"]
RESTAURANTS   = PRIORITY_RESTAURANTS  # McDonald's + Burger King

# Inter-location delay: Gaussian 15-30 s to avoid rate limits
_BETWEEN_LOCATIONS_MEAN = 20
_BETWEEN_LOCATIONS_SIGMA = 4
_BETWEEN_LOCATIONS_LO   = 15
_BETWEEN_LOCATIONS_HI   = 30

# ── Helpers ──────────────────────────────────────────────────────────────────

def _status_icon(completeness: str) -> str:
    return {"full": "✅", "partial": "⚠️ ", "failed": "❌"}.get(completeness, "?")


def _fmt_price(price) -> str:
    return f"${price:.0f}" if price is not None else "—"


def _print_partial(result: ScrapeResult, location_label: str) -> None:
    icon = _status_icon(result.data_completeness)
    rest_name = result.restaurant.name if result.restaurant else "?"
    fee = _fmt_price(result.delivery.fee_mxn if result.delivery else None)
    eta = (
        f"{result.delivery.estimated_time_min}-{result.delivery.estimated_time_max} min"
        if result.delivery and result.delivery.estimated_time_min
        else "—"
    )
    print(f"\n{'─'*60}")
    print(f" {icon}  {location_label}  ×  {rest_name}  [{result.data_completeness}]  {result.scrape_duration_seconds}s")
    print(f"     Delivery: {fee}  ETA: {eta}  Rating: {result.restaurant.rating if result.restaurant else '—'}")
    for p in result.products:
        avail = _fmt_price(p.price_mxn) if p.available else "NOT FOUND"
        orig = f"  ← '{p.original_name}'" if p.original_name and p.original_name != p.name else ""
        print(f"     {p.name:<30} {avail}{orig}")
    if result.promotions:
        vals = ", ".join(f"{pr.value or pr.description[:20]}" for pr in result.promotions[:4])
        print(f"     Promos: {vals}")
    if result.errors:
        print(f"     Errors: {'; '.join(result.errors)}")
    print(f"{'─'*60}")


def _print_table(all_results: list[ScrapeResult]) -> None:
    """Print a consolidated summary table."""
    # Collect all product names across all results
    all_product_names: list[str] = []
    for r in all_results:
        for p in r.products:
            if p.name not in all_product_names:
                all_product_names.append(p.name)

    # Column widths
    loc_w   = 16
    rest_w  = 14
    fee_w   = 8
    eta_w   = 12
    prod_w  = 10  # per product column

    # Header
    header_parts = [
        f"{'Location':<{loc_w}}",
        f"{'Restaurant':<{rest_w}}",
        f"{'Status':<8}",
        f"{'Fee':<{fee_w}}",
        f"{'ETA':<{eta_w}}",
    ]
    for pn in all_product_names:
        short = pn.replace("Combo ", "").replace(" Mediano", "").replace(" piezas", "")
        header_parts.append(f"{short[:prod_w]:<{prod_w}}")

    header = " | ".join(header_parts)
    divider = "-" * len(header)

    print(f"\n{'='*len(header)}")
    print("CONSOLIDATED RESULTS")
    print(f"{'='*len(header)}")
    print(header)
    print(divider)

    for r in all_results:
        loc_label = r.location_id.replace("_", " ").title()
        rest_name = (r.restaurant.name[:rest_w] if r.restaurant else "?")
        icon = _status_icon(r.data_completeness)
        fee = _fmt_price(r.delivery.fee_mxn if r.delivery else None)
        eta = (
            f"{r.delivery.estimated_time_min}-{r.delivery.estimated_time_max}"
            if r.delivery and r.delivery.estimated_time_min else "—"
        )

        row_parts = [
            f"{loc_label:<{loc_w}}",
            f"{rest_name:<{rest_w}}",
            f"{icon} {r.data_completeness[:5]:<6}",
            f"{fee:<{fee_w}}",
            f"{eta:<{eta_w}}",
        ]

        price_by_name = {p.name: p for p in r.products}
        for pn in all_product_names:
            prod = price_by_name.get(pn)
            val = _fmt_price(prod.price_mxn) if prod and prod.available else "—"
            row_parts.append(f"{val:<{prod_w}}")

        print(" | ".join(row_parts))

    print(divider)

    # Footer: completeness counts
    counts = {"full": 0, "partial": 0, "failed": 0}
    for r in all_results:
        counts[r.data_completeness] = counts.get(r.data_completeness, 0) + 1
    total = len(all_results)
    print(
        f"Total: {total}  |  ✅ full: {counts['full']}  "
        f"⚠️  partial: {counts['partial']}  ❌ failed: {counts['failed']}"
    )
    print(f"{'='*len(header)}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

async def run_scale_test() -> list[ScrapeResult]:
    locations = [get_location_by_id(lid) for lid in LOCATION_IDS]
    all_results: list[ScrapeResult] = []

    logger.info(
        f"Scale test: {len(locations)} locations × {len(RESTAURANTS)} restaurants "
        f"= {len(locations) * len(RESTAURANTS)} scrapes"
    )
    logger.info(f"Locations : {[loc.short_name for loc in locations]}")
    logger.info(f"Restaurants: {[r.name for r in RESTAURANTS]}")

    scraper = UberEatsScraper()
    await scraper.setup()

    try:
        for loc_idx, location in enumerate(locations):
            if loc_idx > 0:
                # Inter-location Gaussian delay
                secs = max(
                    _BETWEEN_LOCATIONS_LO,
                    min(
                        _BETWEEN_LOCATIONS_HI,
                        random.gauss(_BETWEEN_LOCATIONS_MEAN, _BETWEEN_LOCATIONS_SIGMA),
                    ),
                )
                logger.info(
                    f"⏳ Waiting {secs:.0f}s between locations "
                    f"(location {loc_idx+1}/{len(locations)})"
                )
                await asyncio.sleep(secs)

            logger.info(
                f"\n{'━'*60}\n"
                f"📍 Location {loc_idx+1}/{len(locations)}: {location.short_name}\n"
                f"{'━'*60}"
            )

            for rest in RESTAURANTS:
                products = get_products_by_restaurant(rest.id)
                logger.info(f"🍔 Scraping {rest.name} @ {location.short_name}")

                try:
                    result = await scraper.scrape_restaurant_at_location(
                        location, rest, products
                    )
                except Exception as exc:
                    # Unexpected exception — build a failed result and keep going
                    logger.error(
                        f"Unhandled exception scraping {rest.name} @ {location.short_name}: {exc}",
                        exc_info=True,
                    )
                    from scrapers.base import ScrapeResult, RestaurantResult
                    result = ScrapeResult(
                        platform="ubereats",
                        location_id=location.id,
                        location_address=location.address,
                        location_lat=location.lat,
                        location_lng=location.lng,
                        zone_type=location.zone_type,
                        zone_label=location.zone_label,
                        city=location.city,
                    )
                    result.restaurant = RestaurantResult(name=rest.name, available=False)
                    result.errors.append(f"Exception: {exc}")
                    result.data_completeness = "failed"

                all_results.append(result)
                _print_partial(result, location.short_name)

    finally:
        await scraper.teardown()

    return all_results


async def main():
    started = datetime.now()
    print(f"\n🚀 Uber Eats scale test started at {started.strftime('%H:%M:%S')}")

    all_results = await run_scale_test()

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\n⏱  Total elapsed: {elapsed:.0f}s ({elapsed/60:.1f} min)")

    _print_table(all_results)

    # Save results to disk
    from config.settings import RAW_DIR
    saved = []
    for r in all_results:
        try:
            path = r.save(RAW_DIR)
            saved.append(str(path))
        except Exception as e:
            logger.warning(f"Could not save result: {e}")
    if saved:
        print(f"💾 Saved {len(saved)} result files to {RAW_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
