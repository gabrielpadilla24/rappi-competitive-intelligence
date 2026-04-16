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

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import RAW_DIR, PROCESSED_DIR
from config.products import get_product_by_id

logger = logging.getLogger("consolidator")

OUTPUT_CSV_NAME = "competitive_data.csv"

# Per-platform WIDE CSV files produced by the run_{platform}_full.py scripts.
WIDE_CSV_FILES: dict[str, str] = {
    "rappi":    "rappi_data.csv",
    "ubereats": "ubereats_data.csv",
    "didifood": "didifood_data.csv",
}

# Product reference_ids that appear as price_<id> / match_<id> columns in the
# WIDE CSVs. Order matches the columns emitted by the production scrape scripts.
WIDE_PRODUCT_IDS: list[str] = [
    "big_mac", "combo_big_mac", "mcnuggets_10",
    "whopper", "combo_whopper",
]

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
# Wide-format bridge (per-platform CSVs → LONG)
# ============================================================

def _nullish(value: Any) -> bool:
    """True if value is None, NaN, empty string, or literal 'nan'."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return s == "" or s.lower() == "nan"


def _wide_val(value: Any, default: Any = "") -> Any:
    return default if _nullish(value) else value


def _canonical_product_name(product_id: str) -> str:
    prod = get_product_by_id(product_id)
    return prod.name if prod is not None else product_id.replace("_", " ").title()


def flatten_wide_row(wide_row: pd.Series) -> list[dict]:
    """
    Convert one WIDE-format CSV row into 0-N LONG-format row dicts.

    Emits one row per non-empty price_<product_id> cell. Rows whose
    data_completeness is "failed" produce no output.
    """
    completeness = str(wide_row.get("data_completeness", "")).strip().lower()
    if completeness == "failed":
        return []

    delivery_fee_raw = wide_row.get("delivery_fee_mxn")
    service_fee_raw  = wide_row.get("service_fee_mxn")

    base = {
        "scrape_id":              _wide_val(wide_row.get("run_id")),
        "timestamp":              _wide_val(wide_row.get("timestamp")),
        "platform":               _wide_val(wide_row.get("platform")),
        "location_id":            _wide_val(wide_row.get("location_id")),
        "location_address":       _wide_val(wide_row.get("location_address")),
        "lat":                    _wide_val(wide_row.get("lat")),
        "lng":                    _wide_val(wide_row.get("lng")),
        "zone_type":              _wide_val(wide_row.get("zone_type")),
        "zone_label":             _wide_val(wide_row.get("zone_label")),
        "city":                   _wide_val(wide_row.get("city")),
        "restaurant_name":        _wide_val(wide_row.get("restaurant_name")),
        "restaurant_available":   _wide_val(wide_row.get("restaurant_available")),
        "restaurant_rating":      _wide_val(wide_row.get("restaurant_rating")),
        "restaurant_review_count": _wide_val(wide_row.get("restaurant_review_count")),
        "delivery_fee_mxn":       _wide_val(delivery_fee_raw),
        "service_fee_mxn":        _wide_val(service_fee_raw),
        "estimated_time_min":     _wide_val(wide_row.get("eta_min_min")),
        "estimated_time_max":     _wide_val(wide_row.get("eta_max_min")),
        "promotions_count":       _wide_val(wide_row.get("promotions_count"), 0),
        "promotions_description": _wide_val(wide_row.get("promotions_values")),
        "data_completeness":      _wide_val(wide_row.get("data_completeness")),
        "errors_count":           _wide_val(wide_row.get("errors_count"), 0),
        "scrape_duration_seconds": _wide_val(wide_row.get("scrape_duration_seconds")),
    }

    delivery_fee_f = float(delivery_fee_raw) if not _nullish(delivery_fee_raw) else None
    service_fee_f  = float(service_fee_raw)  if not _nullish(service_fee_raw)  else None

    rows: list[dict] = []
    for pid in WIDE_PRODUCT_IDS:
        price_raw = wide_row.get(f"price_{pid}")
        if _nullish(price_raw):
            continue
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue

        match_raw = wide_row.get(f"match_{pid}")
        if _nullish(match_raw):
            product_name = _canonical_product_name(pid)
        else:
            product_name = str(match_raw).strip()

        rows.append({
            **base,
            "product_name":         product_name,
            "product_reference_id": pid,
            "product_price_mxn":    price,
            "product_available":    True,
            "total_price_mxn":      _safe(
                _total_price(price, delivery_fee_f, service_fee_f), "",
            ),
        })

    return rows


def consolidate_from_wide_csvs(
    input_dir: Path = PROCESSED_DIR,
    output_dir: Path = PROCESSED_DIR,
    output_filename: str = OUTPUT_CSV_NAME,
) -> Path:
    """
    Read the three per-platform WIDE CSVs from input_dir, flatten each row
    into one LONG row per non-empty product, and write the consolidated CSV.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename

    rows: list[dict] = []
    per_platform: dict[str, dict] = {}

    for platform, fname in WIDE_CSV_FILES.items():
        fp = input_dir / fname
        if not fp.exists():
            logger.warning(f"Missing WIDE CSV for {platform}: {fp}")
            per_platform[platform] = {"wide_rows": 0, "long_rows": 0, "failed": 0}
            continue

        df = pd.read_csv(fp)
        wide_n = len(df)
        long_before = len(rows)
        failed_n = 0

        for _, wide_row in df.iterrows():
            produced = flatten_wide_row(wide_row)
            if not produced and str(
                wide_row.get("data_completeness", "")
            ).strip().lower() == "failed":
                failed_n += 1
            rows.extend(produced)

        per_platform[platform] = {
            "wide_rows": wide_n,
            "long_rows": len(rows) - long_before,
            "failed":    failed_n,
        }

    if not rows:
        logger.error("No rows produced from WIDE CSVs")
        print("No rows produced from WIDE CSVs")
        return output_path

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    completeness: dict[str, int] = {}
    for row in rows:
        c = row.get("data_completeness", "unknown")
        completeness[c] = completeness.get(c, 0) + 1

    print(f"\n{'=' * 55}")
    print(f"Consolidation from WIDE CSVs complete")
    print(f"  Total LONG rows: {len(rows)}")
    print()
    print(f"  Per-platform (wide → long):")
    for platform, stats in sorted(per_platform.items()):
        print(
            f"    {platform:<10}: {stats['wide_rows']:>3} wide → "
            f"{stats['long_rows']:>3} long  (skipped {stats['failed']} failed)"
        )
    print()
    print(f"  Data completeness:")
    for status, count in sorted(completeness.items()):
        print(f"    {status:<8}: {count}")
    print()
    print(f"  Output: {output_path}")
    print(f"{'=' * 55}\n")

    return output_path


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
        default=None,
        help=(
            "Input directory. With --from-csvs, defaults to "
            f"{PROCESSED_DIR} (where the WIDE CSVs live); otherwise {RAW_DIR}."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DIR,
        help=f"Output directory for CSV (default: {PROCESSED_DIR})",
    )
    parser.add_argument(
        "--from-csvs",
        action="store_true",
        help=(
            "Consolidate from the three per-platform WIDE CSVs "
            "(rappi_data.csv / ubereats_data.csv / didifood_data.csv) "
            "instead of raw JSONs. Use this when data/raw/ mixes runs."
        ),
    )
    args = parser.parse_args()

    if args.from_csvs:
        input_dir = args.input if args.input is not None else PROCESSED_DIR
        consolidate_from_wide_csvs(input_dir=input_dir, output_dir=args.output)
    else:
        input_dir = args.input if args.input is not None else RAW_DIR
        consolidate(input_dir=input_dir, output_dir=args.output)


if __name__ == "__main__":
    main()
