"""
Comparative analysis module.
Processes raw scrape data into comparative metrics across platforms.

Five analytical dimensions:
  1. Price positioning (product prices per platform)
  2. Operational advantage (delivery times per zone)
  3. Fee structure (delivery + service fees)
  4. Promotional strategy (promo rates and types)
  5. Geographic variability (prices and fees by zone)

Usage:
    python -m analysis.comparative
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PROCESSED_DIR, REPORTS_DIR

CSV_PATH = PROCESSED_DIR / "competitive_data.csv"
PLATFORMS = ["rappi", "ubereats", "didifood"]
ZONE_ORDER = [
    "high_income",
    "medium_high_income",
    "medium_income",
    "low_income",
    "commercial",
]


# ============================================================
# Data loading
# ============================================================

def load_data() -> pd.DataFrame:
    """Load CSV and return a fully-typed DataFrame with valid (non-failed) rows."""
    if not CSV_PATH.exists():
        print(
            f"ERROR: {CSV_PATH} not found.\n"
            "Run `make sample` or `python -m scripts.generate_sample_data` first."
        )
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)

    # Cast numeric columns that may have read as object due to empty strings
    numeric_cols = [
        "product_price_mxn", "delivery_fee_mxn", "service_fee_mxn",
        "estimated_time_min", "estimated_time_max", "total_price_mxn",
        "restaurant_rating", "restaurant_review_count",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived column: midpoint delivery time
    df["delivery_time_mid"] = (df["estimated_time_min"] + df["estimated_time_max"]) / 2

    # Filter: keep partial + full for quantitative analysis
    valid = df[df["data_completeness"] != "failed"].copy()
    return valid


# ============================================================
# Dimension 1: Price Positioning
# ============================================================

def analyze_price_positioning(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-product price averages by platform, plus delta % vs Rappi baseline.

    Returns columns:
        product, rappi_avg, ubereats_avg, didifood_avg,
        ue_vs_rappi_pct, didi_vs_rappi_pct, cheapest_platform
    """
    rows_with_price = df[df["product_price_mxn"].notna() & (df["product_name"] != "")]

    pivot = (
        rows_with_price
        .groupby(["product_name", "platform"])["product_price_mxn"]
        .mean()
        .unstack("platform")
        .reindex(columns=PLATFORMS)
        .reset_index()
    )
    pivot.columns = ["product", "rappi_avg", "ubereats_avg", "didifood_avg"]

    def _pct_delta(col_b, col_a):
        """(b - a) / a * 100 — positive means b is more expensive than a."""
        return ((col_b - col_a) / col_a * 100).round(1)

    pivot["ue_vs_rappi_pct"] = _pct_delta(pivot["ubereats_avg"], pivot["rappi_avg"])
    pivot["didi_vs_rappi_pct"] = _pct_delta(pivot["didifood_avg"], pivot["rappi_avg"])

    def _cheapest(row):
        options = {
            "rappi": row.get("rappi_avg"),
            "ubereats": row.get("ubereats_avg"),
            "didifood": row.get("didifood_avg"),
        }
        valid = {k: v for k, v in options.items() if pd.notna(v)}
        return min(valid, key=valid.get) if valid else "N/A"

    pivot["cheapest_platform"] = pivot.apply(_cheapest, axis=1)

    for col in ["rappi_avg", "ubereats_avg", "didifood_avg"]:
        pivot[col] = pivot[col].round(2)

    return pivot


# ============================================================
# Dimension 2: Delivery Times
# ============================================================

def analyze_delivery_times(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-zone delivery time averages and std by platform, plus fastest platform.

    Returns columns:
        zone_type, rappi_avg_time, ubereats_avg_time, didifood_avg_time,
        rappi_std, ubereats_std, didifood_std, fastest_platform
    """
    rows = df[df["delivery_time_mid"].notna()]

    pivot_avg = (
        rows.groupby(["zone_type", "platform"])["delivery_time_mid"]
        .mean()
        .unstack("platform")
        .reindex(columns=PLATFORMS)
        .reset_index()
    )
    pivot_avg.columns = ["zone_type", "rappi_avg_time", "ubereats_avg_time", "didifood_avg_time"]

    pivot_std = (
        rows.groupby(["zone_type", "platform"])["delivery_time_mid"]
        .std()
        .unstack("platform")
        .reindex(columns=PLATFORMS)
        .reset_index()
    )
    pivot_std.columns = ["zone_type", "rappi_std", "ubereats_std", "didifood_std"]

    result = pivot_avg.merge(pivot_std, on="zone_type", how="left")

    def _fastest(row):
        options = {
            "rappi": row.get("rappi_avg_time"),
            "ubereats": row.get("ubereats_avg_time"),
            "didifood": row.get("didifood_avg_time"),
        }
        valid = {k: v for k, v in options.items() if pd.notna(v)}
        return min(valid, key=valid.get) if valid else "N/A"

    result["fastest_platform"] = result.apply(_fastest, axis=1)

    for col in ["rappi_avg_time", "ubereats_avg_time", "didifood_avg_time",
                "rappi_std", "ubereats_std", "didifood_std"]:
        result[col] = result[col].round(1)

    return result


# ============================================================
# Dimension 3: Fee Structure
# ============================================================

def analyze_fee_structure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-platform delivery fee, service fee, total fee, and fee as % of product price.

    Returns columns:
        platform, avg_delivery_fee, avg_service_fee, avg_total_fee,
        fee_as_pct_of_product
    """
    rows = df[df["delivery_fee_mxn"].notna()]

    agg = (
        rows.groupby("platform")
        .agg(
            avg_delivery_fee=("delivery_fee_mxn", "mean"),
            avg_service_fee=("service_fee_mxn", "mean"),
            avg_product_price=("product_price_mxn", "mean"),
        )
        .reindex(PLATFORMS)
        .reset_index()
    )

    agg["avg_service_fee"] = agg["avg_service_fee"].fillna(0)
    agg["avg_total_fee"] = (agg["avg_delivery_fee"] + agg["avg_service_fee"]).round(2)
    agg["fee_as_pct_of_product"] = (
        agg["avg_total_fee"] / agg["avg_product_price"] * 100
    ).round(1)

    for col in ["avg_delivery_fee", "avg_service_fee", "avg_product_price"]:
        agg[col] = agg[col].round(2)

    return agg[["platform", "avg_delivery_fee", "avg_service_fee", "avg_total_fee",
                "fee_as_pct_of_product"]]


# ============================================================
# Dimension 4: Promotional Strategy
# ============================================================

def analyze_promotions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-platform promo rate, most common promo type, and sample descriptions.

    Returns columns:
        platform, total_observations, promo_observations, promo_rate_pct,
        most_common_promo_type, sample_promos
    """
    # Deduplicate to observation level (one row per scrape_id + platform)
    obs = df.drop_duplicates(subset=["scrape_id"]).copy()

    results = []
    for platform in PLATFORMS:
        pf = obs[obs["platform"] == platform]
        total = len(pf)
        with_promo = (pf["promotions_count"] > 0).sum()
        rate = round(with_promo / total * 100, 1) if total > 0 else 0.0

        # Collect promo descriptions from the full (non-deduplicated) df
        promo_rows = df[
            (df["platform"] == platform) & (df["promotions_description"].notna())
            & (df["promotions_description"] != "")
        ]
        all_promos = promo_rows["promotions_description"].str.split(" | ").explode()
        all_promos = all_promos[all_promos.str.strip() != ""]

        most_common_type = "N/A"
        sample = "N/A"
        if len(all_promos) > 0:
            counts = all_promos.value_counts()
            sample = " | ".join(counts.head(3).index.tolist())

            # Infer type from keywords
            promo_text = " ".join(all_promos.tolist()).lower()
            if "%" in promo_text or "off" in promo_text or "descuento" in promo_text:
                most_common_type = "discount"
            elif "gratis" in promo_text or "envío" in promo_text or "free" in promo_text:
                most_common_type = "free_delivery"
            elif "cashback" in promo_text:
                most_common_type = "cashback"
            else:
                most_common_type = "bundle"

        results.append({
            "platform": platform,
            "total_observations": total,
            "promo_observations": int(with_promo),
            "promo_rate_pct": rate,
            "most_common_promo_type": most_common_type,
            "sample_promos": sample,
        })

    return pd.DataFrame(results)


# ============================================================
# Dimension 5: Geographic Variability
# ============================================================

def analyze_geographic_variability(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-zone × per-platform averages for price, fee, and time.
    Adds a Rappi rank column (1=cheapest, 3=most expensive) within each zone.

    Returns columns:
        zone_type, zone_label, platform, avg_price, avg_fee,
        avg_time, avg_total_price, rappi_rank
    """
    rows = df[df["product_price_mxn"].notna()]

    agg = (
        rows.groupby(["zone_type", "zone_label", "platform"])
        .agg(
            avg_price=("product_price_mxn", "mean"),
            avg_fee=("delivery_fee_mxn", "mean"),
            avg_time=("delivery_time_mid", "mean"),
            avg_total_price=("total_price_mxn", "mean"),
        )
        .round(2)
        .reset_index()
    )

    # Rank platforms by avg_total_price within each zone (1 = cheapest)
    agg["rank_in_zone"] = agg.groupby("zone_type")["avg_total_price"].rank(
        method="min", ascending=True
    )
    rappi_ranks = (
        agg[agg["platform"] == "rappi"][["zone_type", "rank_in_zone"]]
        .rename(columns={"rank_in_zone": "rappi_rank"})
    )
    agg = agg.merge(rappi_ranks, on="zone_type", how="left")

    return agg


# ============================================================
# Summary printer
# ============================================================

def print_summary(price_df, time_df, fee_df, promo_df, geo_df) -> None:
    sep = "=" * 60
    print(f"\n{sep}")
    print("COMPARATIVE ANALYSIS SUMMARY")
    print(sep)

    # Prices
    print("\n--- PRICE POSITIONING ---")
    if not price_df.empty:
        ue_delta = price_df["ue_vs_rappi_pct"].mean()
        didi_delta = price_df["didi_vs_rappi_pct"].mean()
        ue_str = f"{ue_delta:+.1f}%" if pd.notna(ue_delta) else "sin datos"
        didi_str = f"{didi_delta:+.1f}%" if pd.notna(didi_delta) else "sin datos"
        print(f"  Uber Eats vs Rappi (avg): {ue_str}")
        print(f"  DiDi Food vs Rappi (avg): {didi_str}")
        cheapest_counts = price_df["cheapest_platform"].value_counts()
        for plat, cnt in cheapest_counts.items():
            print(f"  Cheapest platform ({cnt} products): {plat}")

    # Times
    print("\n--- DELIVERY TIMES ---")
    if not time_df.empty:
        for _, row in time_df.iterrows():
            print(
                f"  {row['zone_type']:<25} → fastest: {row['fastest_platform']} "
                f"(Rappi {row.get('rappi_avg_time', 'N/A')} min)"
            )

    # Fees
    print("\n--- FEE STRUCTURE ---")
    if not fee_df.empty:
        for _, row in fee_df.iterrows():
            total_fee = row["avg_total_fee"]
            if pd.isna(total_fee):
                continue
            fee_pct = row["fee_as_pct_of_product"]
            pct_str = f"{fee_pct:.1f}% of product price" if pd.notna(fee_pct) else "% N/A"
            print(f"  {row['platform']:<12} total fee: ${total_fee:.0f} ({pct_str})")

    # Promotions
    print("\n--- PROMOTIONS ---")
    if not promo_df.empty:
        for _, row in promo_df.iterrows():
            print(f"  {row['platform']:<12} promo rate: {row['promo_rate_pct']}%")

    print(f"\n{sep}\n")


# ============================================================
# Main
# ============================================================

def main() -> dict:
    """Run all analysis dimensions and save CSVs to reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data()
    print(f"Loaded {len(df)} valid rows from {CSV_PATH}")

    price_df = analyze_price_positioning(df)
    time_df = analyze_delivery_times(df)
    fee_df = analyze_fee_structure(df)
    promo_df = analyze_promotions(df)
    geo_df = analyze_geographic_variability(df)

    price_df.to_csv(REPORTS_DIR / "analysis_prices.csv", index=False)
    time_df.to_csv(REPORTS_DIR / "analysis_times.csv", index=False)
    fee_df.to_csv(REPORTS_DIR / "analysis_fees.csv", index=False)
    promo_df.to_csv(REPORTS_DIR / "analysis_promotions.csv", index=False)
    geo_df.to_csv(REPORTS_DIR / "analysis_geographic.csv", index=False)

    print_summary(price_df, time_df, fee_df, promo_df, geo_df)
    print(f"Analysis CSVs saved to {REPORTS_DIR}/")

    return {
        "prices": price_df,
        "times": time_df,
        "fees": fee_df,
        "promotions": promo_df,
        "geographic": geo_df,
        "raw": df,
    }


if __name__ == "__main__":
    main()
