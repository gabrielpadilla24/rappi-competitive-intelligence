"""
Recovery run — DiDi Food scraper.

Re-runs only the (location × restaurant) combinations that failed during the
full production run.  Appends to the existing CSV instead of overwriting.

Targets:
  • 4 locations: Satélite, Centro Histórico, Chapultepec, Reforma
  • 2 restaurants: McDonald's, Burger King
  • Total: 8 scrapes

Execution model:
  • Locations processed in batches of BATCH_SIZE (default 2).
  • Between batches: Gaussian pause μ=60 s, σ=10 s, clamped [45, 90].
  • Each (location × restaurant) is retried once after 60 s if it fails.
  • Single browser session per batch; reset between batches.

Authentication:
  • Session cookies are injected automatically from didifood_scraper._SESSION_COOKIES.
  • If you see "Session expired — need fresh cookies" in the log, update the
    token and ttcsid values in scrapers/didifood_scraper.py.

Outputs:
  • logs/didifood_recovery_run.log      — full DEBUG log
  • data/processed/didifood_data.csv    — APPENDED (not overwritten)
  • Console summary table of the 8 recovery scrapes

Usage:
    python run_didifood_recovery.py [--batch-size N] [--dry-run]
"""

import argparse
import asyncio
import csv
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

# ── Project root on PYTHONPATH ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Directories ──────────────────────────────────────────────────────────────
LOGS_DIR      = ROOT / "logs"
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR       = ROOT / "data" / "raw"

for _d in (LOGS_DIR, PROCESSED_DIR, RAW_DIR):
    _d.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "didifood_recovery_run.log"
CSV_FILE = PROCESSED_DIR / "didifood_data.csv"


# ── Logging (dual: file=DEBUG, console=INFO) ─────────────────────────────────
def _setup_logging() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(ch)

    for noisy in ("asyncio", "playwright", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("didifood_recovery")


logger = _setup_logging()

# ── Import scraper (after logging so import errors are captured) ─────────────
from scrapers.didifood_scraper import DididfoodScraper
from scrapers.base import ScrapeResult, RestaurantResult
from config.locations import get_location_by_id, Location
from config.products import (
    PRIORITY_RESTAURANTS, get_products_by_restaurant,
    TargetRestaurant, Product,
)

# ── Constants ────────────────────────────────────────────────────────────────
RECOVERY_LOCATION_IDS = ["satelite", "centro", "chapultepec", "reforma"]

BATCH_SIZE            = 2
BATCH_PAUSE_MEAN      = 60.0
BATCH_PAUSE_SIGMA     = 10.0
BATCH_PAUSE_LO        = 45.0
BATCH_PAUSE_HI        = 90.0
RETRY_WAIT_SECS       = 60

_PRODUCT_IDS: list[str] = [
    "big_mac", "combo_big_mac", "mcnuggets_10",
    "whopper", "combo_whopper",
]

_CSV_FIELDS: list[str] = [
    "run_id", "timestamp", "platform",
    "location_id", "location_address", "zone_type", "zone_label", "city",
    "lat", "lng",
    "restaurant_name", "restaurant_available", "restaurant_rating",
    "restaurant_review_count",
    "delivery_fee_mxn", "service_fee_mxn",
    "eta_min_min", "eta_max_min",
    *[f"price_{pid}" for pid in _PRODUCT_IDS],
    *[f"match_{pid}" for pid in _PRODUCT_IDS],
    "promotions_count", "promotions_values",
    "data_completeness", "retry_attempt",
    "errors_count", "errors",
    "scrape_duration_seconds",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _gauss_clamp(mean: float, sigma: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, random.gauss(mean, sigma)))


def _resolve_recovery_locations() -> list[Location]:
    """Resolve the hard-coded recovery location IDs to Location objects."""
    locations: list[Location] = []
    for lid in RECOVERY_LOCATION_IDS:
        loc = get_location_by_id(lid)
        if loc is None:
            logger.error(f"Unknown location id '{lid}' — skipping")
            continue
        locations.append(loc)
    return locations


def _result_to_row(
    result: ScrapeResult,
    run_id: str,
    retry_attempt: int,
) -> dict:
    """Flatten a ScrapeResult into a CSV row dict."""
    rest = result.restaurant

    price_by_pid: dict[str, object] = {}
    match_by_pid: dict[str, str] = {}
    for p in result.products:
        price_by_pid[p.reference_id] = p.price_mxn if p.available else None
        match_by_pid[p.reference_id] = p.original_name

    delivery    = result.delivery
    promos_vals = "; ".join(
        pr.value or pr.description[:30]
        for pr in result.promotions
        if pr.value or pr.description
    )

    return {
        "run_id":                run_id,
        "timestamp":             result.timestamp,
        "platform":              result.platform,
        "location_id":           result.location_id,
        "location_address":      result.location_address,
        "zone_type":             result.zone_type,
        "zone_label":            result.zone_label,
        "city":                  result.city,
        "lat":                   result.location_lat,
        "lng":                   result.location_lng,
        "restaurant_name":       rest.name if rest else "",
        "restaurant_available":  rest.available if rest else False,
        "restaurant_rating":     rest.rating if rest else "",
        "restaurant_review_count": rest.review_count if rest else "",
        "delivery_fee_mxn":      delivery.fee_mxn if delivery else "",
        "service_fee_mxn":       delivery.service_fee_mxn if delivery else "",
        "eta_min_min":           delivery.estimated_time_min if delivery else "",
        "eta_max_min":           delivery.estimated_time_max if delivery else "",
        **{f"price_{pid}": price_by_pid.get(pid, "") for pid in _PRODUCT_IDS},
        **{f"match_{pid}": match_by_pid.get(pid, "") for pid in _PRODUCT_IDS},
        "promotions_count":      len(result.promotions),
        "promotions_values":     promos_vals,
        "data_completeness":     result.data_completeness,
        "retry_attempt":         retry_attempt,
        "errors_count":          len(result.errors),
        "errors":                "; ".join(result.errors),
        "scrape_duration_seconds": result.scrape_duration_seconds,
    }


def _make_failed_result(
    location: Location,
    restaurant: TargetRestaurant,
    error_msg: str,
) -> ScrapeResult:
    result = ScrapeResult(
        platform="didifood",
        location_id=location.id,
        location_address=location.address,
        location_lat=location.lat,
        location_lng=location.lng,
        zone_type=location.zone_type,
        zone_label=location.zone_label,
        city=location.city,
    )
    result.restaurant = RestaurantResult(name=restaurant.name, available=False)
    result.errors.append(error_msg)
    result.data_completeness = "failed"
    return result


def _print_console_table(all_rows: list[dict]) -> None:
    """Print a compact summary of the recovery scrapes."""
    if not all_rows:
        print("No results to display.")
        return

    W = {"zone": 22, "loc": 14, "rest": 14, "status": 8,
         "fee": 6, "eta": 9, "bm": 7, "cbm": 7, "mc": 7, "wp": 7, "cwp": 7}

    hdr = (
        f"{'Zone':<{W['zone']}} {'Location':<{W['loc']}} {'Restaurant':<{W['rest']}} "
        f"{'Status':<{W['status']}} {'Fee':>{W['fee']}} {'ETA':>{W['eta']}} "
        f"{'BigMac':>{W['bm']}} {'ComboBM':>{W['cbm']}} {'McNug':>{W['mc']}} "
        f"{'Whopr':>{W['wp']}} {'ComboW':>{W['cwp']}}"
    )
    divider = "─" * len(hdr)

    icon = {"full": "✅", "partial": "⚠️ ", "failed": "❌"}.get

    print(f"\n{'═'*len(hdr)}")
    print("DiDi FOOD — RECOVERY RUN RESULTS")
    print(f"{'═'*len(hdr)}")
    print(hdr)
    print(divider)

    prev_zone = None
    for row in sorted(
        all_rows, key=lambda x: (x["zone_label"], x["location_id"], x["restaurant_name"])
    ):
        zone = row["zone_label"]
        if zone != prev_zone:
            if prev_zone is not None:
                print(divider)
            prev_zone = zone

        fee_str = f"${row['delivery_fee_mxn']:.0f}" if row["delivery_fee_mxn"] != "" else "—"
        eta_str = (
            f"{row['eta_min_min']}-{row['eta_max_min']}"
            if row["eta_min_min"] != "" else "—"
        )
        status_str = f"{icon(row['data_completeness'], '?')} {row['data_completeness'][:4]}"

        def price(pid: str) -> str:
            v = row.get(f"price_{pid}", "")
            return f"${v:.0f}" if v != "" and v is not None else "—"

        loc_short  = row["location_id"].replace("_", " ")[:W["loc"]]
        rest_short = row["restaurant_name"][:W["rest"]]

        print(
            f"{zone:<{W['zone']}} {loc_short:<{W['loc']}} {rest_short:<{W['rest']}} "
            f"{status_str:<{W['status']}} {fee_str:>{W['fee']}} {eta_str:>{W['eta']}} "
            f"{price('big_mac'):>{W['bm']}} {price('combo_big_mac'):>{W['cbm']}} "
            f"{price('mcnuggets_10'):>{W['mc']}} "
            f"{price('whopper'):>{W['wp']}} {price('combo_whopper'):>{W['cwp']}}"
        )

    print(divider)

    total   = len(all_rows)
    full    = sum(1 for r in all_rows if r["data_completeness"] == "full")
    partial = sum(1 for r in all_rows if r["data_completeness"] == "partial")
    failed  = sum(1 for r in all_rows if r["data_completeness"] == "failed")
    retried = sum(1 for r in all_rows if r["retry_attempt"] == 2)
    print(
        f"Total recovery scrapes: {total}  |  "
        f"✅ full: {full}  ⚠️  partial: {partial}  ❌ failed: {failed}  "
        f"🔁 retried: {retried}"
    )
    print(f"{'═'*len(hdr)}\n")


# ── Core scraping logic ───────────────────────────────────────────────────────

async def scrape_with_retry(
    scraper: DididfoodScraper,
    location: Location,
    restaurant: TargetRestaurant,
    products: list[Product],
) -> tuple[ScrapeResult, int]:
    """Run one (location × restaurant) scrape with a single retry on failure."""
    for attempt in (1, 2):
        try:
            result = await scraper.scrape_restaurant_at_location(
                location, restaurant, products
            )
        except Exception as exc:
            logger.error(
                f"Unhandled exception [{attempt}/2] "
                f"{restaurant.name} @ {location.short_name}: {exc}",
                exc_info=True,
            )
            result = _make_failed_result(location, restaurant, f"Exception: {exc}")

        if result.data_completeness != "failed":
            return result, attempt

        if attempt == 1:
            logger.warning(
                f"[FAIL→RETRY] {restaurant.name} @ {location.short_name} "
                f"— waiting {RETRY_WAIT_SECS}s before retry. "
                f"Errors: {result.errors}"
            )
            await asyncio.sleep(RETRY_WAIT_SECS)

    return result, 2


async def run_recovery(batch_size: int) -> list[dict]:
    """Main execution loop. Returns a list of CSV row dicts."""
    locations = _resolve_recovery_locations()
    if not locations:
        logger.error("No valid recovery locations resolved — aborting")
        return []

    restaurants = PRIORITY_RESTAURANTS

    batches = [locations[i:i + batch_size] for i in range(0, len(locations), batch_size)]
    total_scrapes = len(locations) * len(restaurants)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger.info("=" * 70)
    logger.info("DiDi Food — Recovery run")
    logger.info(f"  Run ID      : {run_id}")
    logger.info(f"  Locations   : {[loc.short_name for loc in locations]}")
    logger.info(f"  Restaurants : {[r.name for r in restaurants]}")
    logger.info(f"  Batches     : {len(batches)} × {batch_size} locations")
    logger.info(f"  Total scrapes: {total_scrapes}")
    logger.info(f"  Log file    : {LOG_FILE}")
    logger.info(f"  CSV output  : {CSV_FILE} (APPEND mode)")
    logger.info("=" * 70)

    scraper = DididfoodScraper()
    await scraper.setup()

    all_rows: list[dict] = []
    scrape_num = 0

    # APPEND mode — write header only if the CSV doesn't yet exist.
    csv_exists = CSV_FILE.exists() and CSV_FILE.stat().st_size > 0
    csv_file = open(CSV_FILE, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    if not csv_exists:
        writer.writeheader()

    try:
        for batch_idx, batch_locs in enumerate(batches):
            # ── Between-batch pause + browser session reset ───────────────
            if batch_idx > 0:
                pause = _gauss_clamp(
                    BATCH_PAUSE_MEAN, BATCH_PAUSE_SIGMA,
                    BATCH_PAUSE_LO, BATCH_PAUSE_HI,
                )
                logger.info(
                    f"⏳ Batch pause: {pause:.0f}s "
                    f"(batch {batch_idx + 1}/{len(batches)})"
                )
                await asyncio.sleep(pause)

                logger.info("🔄 Browser session reset between batches")
                await scraper.teardown()
                await scraper.setup()
                scraper._restaurant_search_count = 0
                logger.info("🔄 Browser session reset complete")

            logger.info(
                f"\n{'━'*60}\n"
                f"📦 Batch {batch_idx + 1}/{len(batches)}: "
                f"{[loc.short_name for loc in batch_locs]}\n"
                f"{'━'*60}"
            )

            for location in batch_locs:
                for restaurant in restaurants:
                    scrape_num += 1
                    progress = f"[{scrape_num:02d}/{total_scrapes}]"
                    logger.info(
                        f"{progress} {restaurant.name} @ {location.short_name}"
                    )

                    products = get_products_by_restaurant(restaurant.id)
                    result, attempt = await scrape_with_retry(
                        scraper, location, restaurant, products
                    )

                    try:
                        result.save(RAW_DIR)
                    except Exception as e:
                        logger.warning(f"Could not save raw JSON: {e}")

                    row = _result_to_row(result, run_id, attempt)
                    all_rows.append(row)
                    writer.writerow(row)
                    csv_file.flush()

                    icon = {"full": "✅", "partial": "⚠️ ", "failed": "❌"}.get(
                        result.data_completeness, "?"
                    )
                    retry_tag = " (retry)" if attempt == 2 else ""
                    logger.info(
                        f"{progress} {icon} {result.data_completeness}{retry_tag} — "
                        f"fee={result.delivery.fee_mxn if result.delivery else '—'} "
                        f"eta={result.delivery.estimated_time_min if result.delivery else '—'}-"
                        f"{result.delivery.estimated_time_max if result.delivery else '—'} min"
                    )

    finally:
        csv_file.close()
        await scraper.teardown()

    return all_rows


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DiDi Food recovery scrape")
    p.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Locations per batch (default {BATCH_SIZE})",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print execution plan and exit without scraping",
    )
    return p.parse_args()


def _print_plan(batch_size: int) -> None:
    locations   = _resolve_recovery_locations()
    restaurants = PRIORITY_RESTAURANTS
    batches     = [locations[i:i + batch_size] for i in range(0, len(locations), batch_size)]

    print(f"\nDRY RUN — Recovery execution plan")
    print(f"  Locations   : {[loc.short_name for loc in locations]}")
    print(f"  Restaurants : {[r.name for r in restaurants]}")
    print(f"  Batch size  : {batch_size}")
    print(f"  Batches     : {len(batches)}")
    print(f"  Total scrapes: {len(locations) * len(restaurants)}")
    est_secs_per_scrape = 55
    est_batch_pause     = BATCH_PAUSE_MEAN * max(0, len(batches) - 1)
    est_total = len(locations) * len(restaurants) * est_secs_per_scrape + est_batch_pause
    print(f"  Est. duration: {est_total/60:.0f}–{est_total*1.3/60:.0f} min")
    print()
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}: {[loc.short_name for loc in batch]}")
    print(f"\n  Output CSV : {CSV_FILE} (APPEND)")
    print(f"  Log file   : {LOG_FILE}\n")


async def main() -> None:
    args = _parse_args()

    if args.dry_run:
        _print_plan(args.batch_size)
        return

    started = datetime.now()
    logger.info(f"Recovery run started: {started.isoformat()}")

    all_rows = await run_recovery(batch_size=args.batch_size)

    elapsed = (datetime.now() - started).total_seconds()
    logger.info(f"Recovery run completed in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    logger.info(f"CSV appended: {CSV_FILE}")
    logger.info(f"Log saved: {LOG_FILE}")

    _print_console_table(all_rows)

    print(f"⏱  Total elapsed: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"📄 CSV  → {CSV_FILE} (appended)")
    print(f"📋 Log  → {LOG_FILE}")

    failed = sum(1 for r in all_rows if r["data_completeness"] == "failed")
    if failed:
        logger.warning(f"{failed} recovery scrape(s) failed after retry")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
