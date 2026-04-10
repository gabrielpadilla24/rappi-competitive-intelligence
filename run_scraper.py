"""
Main entry point for running the competitive intelligence scraper.

Usage:
    python run_scraper.py --locations all --platforms all
    python run_scraper.py --mode quick
    python run_scraper.py --platforms rappi,ubereats --zone-type high_income
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from config.settings import (
    RAW_DIR, PROCESSED_DIR, ACTIVE_PLATFORMS,
    DELAY_BETWEEN_LOCATIONS, DELAY_BETWEEN_PLATFORMS,
)
from config.locations import (
    LOCATIONS, QUICK_LOCATIONS, FULL_LOCATIONS,
    get_locations_by_zone, get_location_by_id,
)
from config.products import (
    PRIORITY_RESTAURANTS, ALL_RESTAURANTS,
    get_products_by_restaurant,
)
from scrapers.base import ScrapeResult
from scrapers.utils import random_delay


# ============================================================
# Logging Setup
# ============================================================

def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the scraper."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                RAW_DIR / f"scrape_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            ),
        ],
    )


# ============================================================
# Scraper Factory
# ============================================================

def get_scraper(platform: str):
    """Factory function to get the appropriate scraper instance."""
    if platform == "rappi":
        from scrapers.rappi_scraper import RappiScraper
        return RappiScraper()
    elif platform == "ubereats":
        from scrapers.ubereats_scraper import UberEatsScraper
        return UberEatsScraper()
    elif platform == "didifood":
        from scrapers.didifood_scraper import DidiFloodScraper
        return DidiFloodScraper()
    else:
        raise ValueError(f"Unknown platform: {platform}")


# ============================================================
# Main Scraping Loop
# ============================================================

async def run_scraping(
    locations: list,
    platforms: list[str],
    restaurants: list,
) -> list[ScrapeResult]:
    """
    Main scraping orchestration loop.
    Iterates over locations × platforms × restaurants.
    """
    logger = logging.getLogger("runner")
    all_results: list[ScrapeResult] = []
    total_combos = len(locations) * len(platforms) * len(restaurants)

    logger.info(f"=" * 60)
    logger.info(f"Starting scrape run")
    logger.info(f"  Locations:   {len(locations)}")
    logger.info(f"  Platforms:   {', '.join(platforms)}")
    logger.info(f"  Restaurants: {', '.join(r.name for r in restaurants)}")
    logger.info(f"  Total combinations: {total_combos}")
    logger.info(f"=" * 60)

    start_time = time.time()
    completed = 0
    errors = 0

    for platform_name in platforms:
        logger.info(f"\n{'─' * 40}")
        logger.info(f"Platform: {platform_name.upper()}")
        logger.info(f"{'─' * 40}")

        try:
            scraper = get_scraper(platform_name)
            await scraper.setup()

            for location in locations:
                logger.info(f"\n📍 Location: {location.short_name} ({location.zone_type})")

                for restaurant in restaurants:
                    products = get_products_by_restaurant(restaurant.id)
                    logger.info(f"  🏪 {restaurant.name} — {len(products)} products")

                    try:
                        result = await scraper.scrape_restaurant_at_location(
                            location=location,
                            restaurant=restaurant,
                            products=products,
                        )

                        # Save individual result
                        filepath = result.save()
                        all_results.append(result)

                        completed += 1
                        status = "✅" if result.data_completeness == "full" else (
                            "⚠️" if result.data_completeness == "partial" else "❌"
                        )
                        logger.info(
                            f"  {status} {result.data_completeness} "
                            f"({result.scrape_duration_seconds}s) → {filepath.name}"
                        )

                    except Exception as e:
                        errors += 1
                        logger.error(f"  ❌ Failed: {e}")

                    # Delay between restaurants
                    await random_delay(2, 4)

                # Delay between locations
                await asyncio.sleep(DELAY_BETWEEN_LOCATIONS)

            await scraper.teardown()

        except NotImplementedError:
            logger.warning(f"⏭️  {platform_name} scraper not yet implemented — skipping")
            continue
        except Exception as e:
            logger.error(f"Platform {platform_name} failed: {e}", exc_info=True)
            continue

        # Delay between platforms
        await asyncio.sleep(DELAY_BETWEEN_PLATFORMS)

    # Summary
    elapsed = time.time() - start_time
    logger.info(f"\n{'=' * 60}")
    logger.info(f"SCRAPE COMPLETE")
    logger.info(f"  Total time:    {elapsed:.0f}s ({elapsed/60:.1f}m)")
    logger.info(f"  Completed:     {completed}/{total_combos}")
    logger.info(f"  Errors:        {errors}")
    logger.info(f"  Success rate:  {(completed-errors)/max(completed,1)*100:.0f}%")
    logger.info(f"  Results saved: {RAW_DIR}")
    logger.info(f"{'=' * 60}")

    return all_results


def save_consolidated_results(results: list[ScrapeResult]) -> Path:
    """Save all results as a single consolidated JSON file."""
    filepath = PROCESSED_DIR / f"consolidated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    data = [r.to_dict() for r in results]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Competitive Intelligence Scraper for Delivery Platforms"
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "full", "all"],
        default="full",
        help="Scraping mode: quick (6 locations), full (23), all (25 + secondary cities)",
    )
    parser.add_argument(
        "--locations",
        type=str,
        default="",
        help="Comma-separated location IDs (overrides --mode)",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        default="",
        help="Comma-separated platforms: rappi,ubereats,didifood",
    )
    parser.add_argument(
        "--zone-type",
        type=str,
        default="",
        help="Filter by zone type: high_income, medium_income, etc.",
    )
    parser.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate synthetic sample data instead of live scraping (for development)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger("runner")

    # Determine locations
    if args.locations:
        location_ids = [x.strip() for x in args.locations.split(",")]
        locations = [get_location_by_id(lid) for lid in location_ids]
        locations = [l for l in locations if l is not None]
    elif args.zone_type:
        locations = get_locations_by_zone(args.zone_type)
    elif args.mode == "quick":
        locations = QUICK_LOCATIONS
    elif args.mode == "all":
        locations = LOCATIONS
    else:
        locations = FULL_LOCATIONS

    if not locations:
        logger.error("No locations selected. Check your --locations or --zone-type.")
        sys.exit(1)

    # Determine platforms
    if args.platforms:
        platforms = [x.strip() for x in args.platforms.split(",")]
    else:
        platforms = ACTIVE_PLATFORMS

    # Determine restaurants
    restaurants = PRIORITY_RESTAURANTS

    # Generate sample data or run live scrapers
    if args.generate_sample:
        logger.info("Generating synthetic sample data (--generate-sample mode)")
        from scripts.generate_sample_data import generate_sample_data
        generate_sample_data(locations=locations)
    else:
        results = asyncio.run(run_scraping(locations, platforms, restaurants))
        if results:
            consolidated_path = save_consolidated_results(results)
            logger.info(f"Consolidated results: {consolidated_path}")

    # Always consolidate raw JSONs into CSV after any run
    logger.info("Consolidating raw JSONs into CSV...")
    from scripts.consolidate_data import consolidate
    csv_path = consolidate()
    logger.info(f"CSV ready: {csv_path}")


if __name__ == "__main__":
    main()
