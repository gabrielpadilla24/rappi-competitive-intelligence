"""
Consolidate raw JSON scrape results into a clean CSV.

Reads all *.json files from data/raw/ and writes a flat, analysis-ready
CSV to data/processed/competitive_data.csv.

Schema (one row per product per observation):
    scrape_id, timestamp, platform, location_id, location_address,
    lat, lng, zone_type, zone_label, city,
    restaurant_name, restaurant_available, restaurant_rating, restaurant_review_count,
    product_name, product_reference_id, product_price_mxn, product_available,
    delivery_fee_mxn, service_fee_mxn, estimated_time_min, estimated_time_max,
    total_price_mxn, promotions_count, promotions_description,
    data_completeness, errors_count, scrape_duration_seconds

Usage:
    python -m scripts.consolidate_data
    python -m scripts.consolidate_data --input data/raw/ --output data/processed/
"""

import argparse
import csv
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import RAW_DIR, PROCESSED_DIR

logger = logging.getLogger("consolidator")

OUTPUT_CSV_NAME = "competitive_data.csv"

CSV_COLUMNS = [
    "scrape_id",
    "timestamp",
    "platform",
    "location_id",
    "location_address",
    "lat",
    "lng",
    "zone_type",
    "zone_label",
    "city",
    "restaurant_name",
    "restaurant_available",
    "restaurant_rating",
    "restaurant_review_count",
    "product_name",
    "product_reference_id",
    "product_price_mxn",
    "product_available",
    "delivery_fee_mxn",
    "service_fee_mxn",
    "estimated_time_min",
    "estimated_time_max",
    "total_price_mxn",
    "promotions_count",
    "promotions_description",
    "data_completeness",
    "errors_count",
    "scrape_duration_seconds",
]


# ============================================================
# Parsing helpers
# ============================================================

def _safe(value: Any, default=None):
    return value if value is not None else default


def _total_price(
    product_price: Optional[float],
    delivery_fee: Optional[float],
    service_fee: Optional[float],
) -> Optional[float]:
    """Sum of product + delivery + service fees. None if any component is missing."""
    if product_price is None or delivery_fee is None:
        return None
    svc = service_fee or 0.0
    return round(product_price + delivery_fee + svc, 2)


def _promotions_description(promotions: list[dict]) -> str:
    """Concatenate promotion descriptions with ' | '."""
    descriptions = [p.get("description", "") for p in promotions if p.get("description")]
    return " | ".join(descriptions)


def load_json(filepath: Path) -> Optional[dict]:
    """Load a JSON file, returning None on parse errors."""
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Skipping corrupt JSON {filepath.name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Skipping {filepath.name}: {e}")
        return None


def flatten_result(data: dict) -> list[dict]:
    """
    Convert one ScrapeResult dict into one or more CSV rows (one per product).
    Returns a list of row dicts matching CSV_COLUMNS.
    """
    restaurant = data.get("restaurant") or {}
    delivery = data.get("delivery") or {}
    products = data.get("products") or []
    promotions = data.get("promotions") or []
    errors = data.get("errors") or []

    # Shared fields across all rows from this observation
    base = {
        "scrape_id":              _safe(data.get("scrape_id"), ""),
        "timestamp":              _safe(data.get("timestamp"), ""),
        "platform":               _safe(data.get("platform"), ""),
        "location_id":            _safe(data.get("location_id"), ""),
        "location_address":       _safe(data.get("location_address"), ""),
        "lat":                    _safe(data.get("location_lat"), ""),
        "lng":                    _safe(data.get("location_lng"), ""),
        "zone_type":              _safe(data.get("zone_type"), ""),
        "zone_label":             _safe(data.get("zone_label"), ""),
        "city":                   _safe(data.get("city"), ""),
        "restaurant_name":        _safe(restaurant.get("name"), ""),
        "restaurant_available":   _safe(restaurant.get("available"), ""),
        "restaurant_rating":      _safe(restaurant.get("rating"), ""),
        "restaurant_review_count": _safe(restaurant.get("review_count"), ""),
        "delivery_fee_mxn":       _safe(delivery.get("fee_mxn"), ""),
        "service_fee_mxn":        _safe(delivery.get("service_fee_mxn"), ""),
        "estimated_time_min":     _safe(delivery.get("estimated_time_min"), ""),
        "estimated_time_max":     _safe(delivery.get("estimated_time_max"), ""),
        "promotions_count":       len(promotions),
        "promotions_description": _promotions_description(promotions),
        "data_completeness":      _safe(data.get("data_completeness"), ""),
        "errors_count":           len(errors),
        "scrape_duration_seconds": _safe(data.get("scrape_duration_seconds"), ""),
    }

    if not products:
        # No products — emit one row with empty product fields
        row = {**base,
               "product_name": "",
               "product_reference_id": "",
               "product_price_mxn": "",
               "product_available": "",
               "total_price_mxn": ""}
        return [row]

    rows = []
    for product in products:
        price = product.get("price_mxn")
        delivery_fee = delivery.get("fee_mxn")
        service_fee = delivery.get("service_fee_mxn")

        row = {
            **base,
            "product_name":         _safe(product.get("name"), ""),
            "product_reference_id": _safe(product.get("reference_id"), ""),
            "product_price_mxn":    _safe(price, ""),
            "product_available":    _safe(product.get("available"), ""),
            "total_price_mxn":      _safe(
                _total_price(
                    float(price) if price is not None else None,
                    float(delivery_fee) if delivery_fee is not None else None,
                    float(service_fee) if service_fee is not None else None,
                ),
                "",
            ),
        }
        rows.append(row)

    return rows


# ============================================================
# Main consolidation function
# ============================================================

def consolidate(
    input_dir: Path = RAW_DIR,
    output_dir: Path = PROCESSED_DIR,
    output_filename: str = OUTPUT_CSV_NAME,
) -> Path:
    """
    Read all JSON files in input_dir, flatten them, and write a CSV.

    Returns the path to the output CSV.
    """
    json_files = sorted(input_dir.glob("*.json"))
    # Exclude log files accidentally named .json (they won't parse anyway, but skip early)
    json_files = [f for f in json_files if not f.name.startswith("scrape_log")]

    if not json_files:
        logger.warning(f"No JSON files found in {input_dir}")
        print(f"No JSON files found in {input_dir}")
        return output_dir / output_filename

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename

    rows: list[dict] = []
    loaded = 0
    skipped = 0

    for filepath in json_files:
        data = load_json(filepath)
        if data is None:
            skipped += 1
            continue
        try:
            file_rows = flatten_result(data)
            rows.extend(file_rows)
            loaded += 1
        except Exception as e:
            logger.warning(f"Could not flatten {filepath.name}: {e}")
            skipped += 1

    if not rows:
        logger.error("No valid data to consolidate")
        print("No valid data to consolidate")
        return output_path

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    platforms = {}
    completeness = {}
    for row in rows:
        p = row.get("platform", "unknown")
        c = row.get("data_completeness", "unknown")
        platforms[p] = platforms.get(p, 0) + 1
        completeness[c] = completeness.get(c, 0) + 1

    print(f"\n{'=' * 55}")
    print(f"Consolidation complete")
    print(f"  JSON files processed: {loaded}")
    print(f"  JSON files skipped:   {skipped}")
    print(f"  Total CSV rows:       {len(rows)}")
    print(f"")
    print(f"  Rows per platform:")
    for plat, count in sorted(platforms.items()):
        print(f"    {plat:<12}: {count}")
    print(f"")
    print(f"  Data completeness:")
    for status, count in sorted(completeness.items()):
        print(f"    {status:<8}: {count}")
    print(f"")
    print(f"  Output: {output_path}")
    print(f"{'=' * 55}\n")

    return output_path


# ============================================================
# CLI
# ============================================================

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Consolidate raw JSON scrape results into a CSV"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=RAW_DIR,
        help=f"Input directory with JSON files (default: {RAW_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DIR,
        help=f"Output directory for CSV (default: {PROCESSED_DIR})",
    )
    args = parser.parse_args()

    consolidate(input_dir=args.input, output_dir=args.output)


if __name__ == "__main__":
    main()
