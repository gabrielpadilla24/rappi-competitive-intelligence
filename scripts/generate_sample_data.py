"""
Generate realistic synthetic data for development and testing.

Simulates a full scraper run without hitting live platforms.
Prices, fees, and timings reflect CDMX delivery market conditions (2025).

Usage:
    python -m scripts.generate_sample_data           # Quick (priority-1 locations)
    python -m scripts.generate_sample_data --all      # All 25 locations
    python -m scripts.generate_sample_data --clean    # Clean data/raw/ first
"""

import argparse
import json
import random
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Allow running as module or directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.locations import QUICK_LOCATIONS, ALL_LOCATIONS, Location
from config.products import (
    PRIORITY_RESTAURANTS, get_products_by_restaurant,
    Product, TargetRestaurant,
)
from config.settings import RAW_DIR
from scrapers.base import (
    ScrapeResult, RestaurantResult, ProductResult,
    DeliveryInfo, PromotionInfo,
)


# ============================================================
# Reproducibility
# ============================================================

SEED = 42


# ============================================================
# Price tables (MXN, 2025)
# ============================================================

# Base prices per product (mid-range estimate)
BASE_PRICES: dict[str, tuple[float, float]] = {
    "big_mac":        (89.0,  99.0),
    "combo_big_mac":  (149.0, 169.0),
    "mcnuggets_10":   (109.0, 125.0),
    "whopper":        (99.0,  115.0),
    "combo_whopper":  (159.0, 179.0),
    "coca_cola_500":  (22.0,  28.0),
    "agua_bonafont_1l": (16.0, 22.0),
}

# Platform multipliers (applied on top of base price)
PLATFORM_PRICE_MULTIPLIER: dict[str, tuple[float, float]] = {
    "rappi":    (1.00, 1.00),   # reference
    "ubereats": (1.03, 1.08),   # +3–8%
    "didifood": (0.95, 1.02),   # -5–+2%
}

# Zone multipliers
ZONE_PRICE_MULTIPLIER: dict[str, tuple[float, float]] = {
    "high_income":         (1.05, 1.10),
    "medium_high_income":  (1.00, 1.05),
    "medium_income":       (1.00, 1.00),
    "low_income":          (0.97, 1.02),
    "commercial":          (1.02, 1.07),
}

# Delivery fees (MXN)
DELIVERY_FEE_RANGE: dict[str, tuple[float, float]] = {
    "rappi":    (19.0, 49.0),
    "ubereats": (15.0, 45.0),
    "didifood": (0.0,  35.0),
}

# Zone fee multipliers (peripheral zones cost more)
ZONE_FEE_MULTIPLIER: dict[str, tuple[float, float]] = {
    "high_income":         (0.80, 1.00),
    "medium_high_income":  (0.90, 1.05),
    "medium_income":       (1.00, 1.10),
    "low_income":          (1.20, 1.50),
    "commercial":          (0.90, 1.05),
}

# Service fees (MXN)
SERVICE_FEE_RANGE: dict[str, tuple[float, float]] = {
    "rappi":    (9.0,  19.0),
    "ubereats": (12.0, 25.0),
    "didifood": (0.0,  10.0),
}

# Delivery time ranges (minutes)
DELIVERY_TIME_RANGE: dict[str, tuple[int, int]] = {
    "rappi":    (20, 45),
    "ubereats": (25, 50),
    "didifood": (15, 40),
}

# Zone time offsets (minutes added/removed)
ZONE_TIME_OFFSET: dict[str, tuple[int, int]] = {
    "high_income":         (-10, -5),
    "medium_high_income":  (-5,  0),
    "medium_income":       (0,   5),
    "low_income":          (5,  15),
    "commercial":          (-8, -3),
}

# Ratings
RESTAURANT_RATINGS: dict[str, tuple[float, float]] = {
    "mcdonalds":   (4.0, 4.6),
    "burger_king": (3.8, 4.4),
    "oxxo":        (4.0, 4.5),
}

# Review counts
REVIEW_COUNT_RANGE: dict[str, tuple[int, int]] = {
    "rappi":    (200,  2000),
    "ubereats": (500,  5000),
    "didifood": (100,  1500),
}

# Sample promotions pool
SAMPLE_PROMOTIONS: dict[str, list[dict]] = {
    "rappi": [
        {"type": "discount",      "description": "15% OFF en tu primer pedido",         "value": "15%"},
        {"type": "free_delivery", "description": "Envío gratis en pedidos +$149",        "value": "$0 envío"},
        {"type": "bundle",        "description": "2x1 en McFlurry",                      "value": "2x1"},
        {"type": "cashback",      "description": "10% de cashback en RappiPay",          "value": "10% cashback"},
    ],
    "ubereats": [
        {"type": "discount",      "description": "$50 OFF en tu pedido",                 "value": "$50 off"},
        {"type": "free_delivery", "description": "Envío $0 con Uber One",                "value": "$0 envío"},
        {"type": "discount",      "description": "20% OFF hasta $80",                    "value": "20%"},
        {"type": "bundle",        "description": "Combo + postre por $30 más",           "value": "$30 add-on"},
    ],
    "didifood": [
        {"type": "discount",      "description": "30% OFF hasta $70",                   "value": "30%"},
        {"type": "free_delivery", "description": "Envío gratis sin mínimo",              "value": "$0 envío"},
        {"type": "discount",      "description": "$40 de descuento con DiDi Club",       "value": "$40 off"},
    ],
}


# ============================================================
# Generator helpers
# ============================================================

def _round2(value: float) -> float:
    return round(value, 2)


def _gen_price(product_id: str, platform: str, zone_type: str) -> float:
    base_lo, base_hi = BASE_PRICES.get(product_id, (50.0, 100.0))
    base = random.uniform(base_lo, base_hi)

    plat_lo, plat_hi = PLATFORM_PRICE_MULTIPLIER[platform]
    zone_lo, zone_hi = ZONE_PRICE_MULTIPLIER[zone_type]

    price = base * random.uniform(plat_lo, plat_hi) * random.uniform(zone_lo, zone_hi)
    # Round to nearest peso (common in MX)
    return _round2(round(price))


def _gen_delivery_fee(platform: str, zone_type: str) -> float:
    lo, hi = DELIVERY_FEE_RANGE[platform]
    fee = random.uniform(lo, hi)
    zone_lo, zone_hi = ZONE_FEE_MULTIPLIER[zone_type]
    fee *= random.uniform(zone_lo, zone_hi)
    # DiDi often has free delivery
    if platform == "didifood" and random.random() < 0.4:
        return 0.0
    return _round2(round(max(fee, 0)))


def _gen_service_fee(platform: str) -> float:
    lo, hi = SERVICE_FEE_RANGE[platform]
    fee = random.uniform(lo, hi)
    # DiDi often has $0 service fee
    if platform == "didifood" and random.random() < 0.5:
        return 0.0
    return _round2(round(fee))


def _gen_delivery_time(platform: str, zone_type: str) -> tuple[int, int]:
    lo, hi = DELIVERY_TIME_RANGE[platform]
    off_lo, off_hi = ZONE_TIME_OFFSET[zone_type]
    t_min = max(10, lo + random.randint(off_lo, off_hi))
    t_max = max(t_min + 5, hi + random.randint(off_lo, off_hi))
    return t_min, t_max


def _gen_rating(restaurant_id: str) -> float:
    lo, hi = RESTAURANT_RATINGS.get(restaurant_id, (3.8, 4.5))
    return round(random.uniform(lo, hi), 1)


def _gen_review_count(platform: str) -> int:
    lo, hi = REVIEW_COUNT_RANGE[platform]
    return random.randint(lo, hi)


def _gen_promotions(platform: str) -> list[PromotionInfo]:
    if random.random() > 0.40:  # ~40% chance of having a promo
        return []
    pool = SAMPLE_PROMOTIONS.get(platform, [])
    if not pool:
        return []
    promo_data = random.choice(pool)
    return [PromotionInfo(
        type=promo_data["type"],
        description=promo_data["description"],
        value=promo_data["value"],
    )]


def _jitter_timestamp(base: datetime, index: int) -> str:
    """Spread timestamps to simulate sequential scraping."""
    offset = timedelta(seconds=index * random.uniform(25, 45))
    return (base + offset).isoformat()


# ============================================================
# Core generation function
# ============================================================

def generate_result(
    location: Location,
    platform: str,
    restaurant: TargetRestaurant,
    products: list[Product],
    timestamp_base: datetime,
    index: int,
) -> ScrapeResult:
    """Generate one synthetic ScrapeResult observation."""

    result = ScrapeResult(
        platform=platform,
        location_id=location.id,
        location_address=location.address,
        location_lat=location.lat,
        location_lng=location.lng,
        zone_type=location.zone_type,
        zone_label=location.zone_label,
        city=location.city,
    )
    result.timestamp = _jitter_timestamp(timestamp_base, index)

    # DiDi Food: ~30% complete failures, rest partial
    if platform == "didifood":
        if random.random() < 0.30:
            result.data_completeness = "failed"
            result.errors = ["DiDi Food web scraping limited — mobile-only platform"]
            result.restaurant = RestaurantResult(name=restaurant.name, available=False)
            result.scrape_duration_seconds = round(random.uniform(5, 15), 2)
            return result

    # Restaurant info
    result.restaurant = RestaurantResult(
        name=f"{restaurant.name}",
        platform_id=f"{platform}_{restaurant.id}_{location.id}",
        available=True,
        rating=_gen_rating(restaurant.id),
        review_count=_gen_review_count(platform),
    )

    # Delivery info
    t_min, t_max = _gen_delivery_time(platform, location.zone_type)
    result.delivery = DeliveryInfo(
        fee_mxn=_gen_delivery_fee(platform, location.zone_type),
        service_fee_mxn=_gen_service_fee(platform),
        estimated_time_min=t_min,
        estimated_time_max=t_max,
        free_delivery_threshold_mxn=149.0 if random.random() < 0.3 else None,
        surge_active=random.random() < 0.08,  # 8% chance of surge
    )

    # Products
    errors: list[str] = []
    for product in products:
        # ~5% chance product is unavailable
        if random.random() < 0.05:
            result.products.append(ProductResult(
                name=product.name,
                reference_id=product.id,
                available=False,
            ))
            errors.append(f"Product '{product.name}' unavailable")
            continue

        price = _gen_price(product.id, platform, location.zone_type)
        result.products.append(ProductResult(
            name=product.name,
            reference_id=product.id,
            price_mxn=price,
            available=True,
            original_name=product.name,
        ))

    # Promotions
    result.promotions = _gen_promotions(platform)
    result.errors = errors
    result.scrape_duration_seconds = round(random.uniform(8, 35), 2)

    # Completeness
    if platform == "didifood":
        # DiDi partial: occasionally missing service_fee
        if random.random() < 0.4:
            result.delivery.service_fee_mxn = None
            result.data_completeness = "partial"
        else:
            result.data_completeness = "partial"  # DiDi always partial (web limitation)
    elif errors:
        result.data_completeness = "partial"
    else:
        result.data_completeness = "full"

    return result


# ============================================================
# Main generator
# ============================================================

def generate_sample_data(
    locations=None,
    output_dir: Path = RAW_DIR,
    clean: bool = False,
    seed: int = SEED,
) -> list[Path]:
    """
    Generate synthetic ScrapeResult JSONs.

    Args:
        locations: List of Location objects. Defaults to QUICK_LOCATIONS.
        output_dir: Where to write JSONs.
        clean: If True, delete all existing JSONs before generating.
        seed: Random seed for reproducibility.

    Returns:
        List of file paths created.
    """
    random.seed(seed)

    if locations is None:
        locations = QUICK_LOCATIONS

    if clean:
        for f in output_dir.glob("*.json"):
            f.unlink()
        print(f"Cleaned {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    platforms = ["rappi", "ubereats", "didifood"]
    restaurants = PRIORITY_RESTAURANTS
    timestamp_base = datetime.now(timezone.utc)

    created_files: list[Path] = []
    stats: dict[str, int] = {p: 0 for p in platforms}
    completeness_counts: dict[str, int] = {"full": 0, "partial": 0, "failed": 0}

    index = 0
    for platform in platforms:
        for location in locations:
            for restaurant in restaurants:
                products = get_products_by_restaurant(restaurant.id)
                result = generate_result(
                    location=location,
                    platform=platform,
                    restaurant=restaurant,
                    products=products,
                    timestamp_base=timestamp_base,
                    index=index,
                )
                filepath = result.save(output_dir)
                created_files.append(filepath)
                stats[platform] += 1
                completeness_counts[result.data_completeness] += 1
                index += 1

    # Print summary
    total = len(created_files)
    print(f"\n{'=' * 55}")
    print(f"Sample data generated: {total} observations")
    print(f"  Locations:  {len(locations)}")
    print(f"  Platforms:  {', '.join(platforms)}")
    print(f"  Restaurants: {', '.join(r.name for r in restaurants)}")
    print(f"")
    print(f"  Per platform:")
    for plat, count in stats.items():
        print(f"    {plat:<12}: {count}")
    print(f"")
    print(f"  Data completeness:")
    for status, count in completeness_counts.items():
        pct = count / total * 100 if total else 0
        print(f"    {status:<8}: {count:>3}  ({pct:.0f}%)")
    print(f"")
    print(f"  Output: {output_dir}")
    print(f"{'=' * 55}\n")

    return created_files


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic competitive intelligence data"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Use all 25 locations (default: priority-1 only)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing JSON files in data/raw/ before generating",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Random seed for reproducibility (default: {SEED})",
    )
    args = parser.parse_args()

    locations = ALL_LOCATIONS if args.all else QUICK_LOCATIONS
    generate_sample_data(locations=locations, clean=args.clean, seed=args.seed)


if __name__ == "__main__":
    main()
