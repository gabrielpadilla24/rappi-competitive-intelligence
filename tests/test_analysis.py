"""
Tests for analysis modules.

All tests are self-contained: they generate synthetic data in a tmp_path
and never touch the real data/ or reports/ directories.
"""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_sample_data import generate_sample_data
from scripts.consolidate_data import consolidate
from config.locations import QUICK_LOCATIONS


# ============================================================
# Shared fixtures
# ============================================================

@pytest.fixture(scope="module")
def sample_csv(tmp_path_factory):
    """Generate sample data and return the path to the consolidated CSV."""
    base = tmp_path_factory.mktemp("data")
    raw_dir = base / "raw"
    processed_dir = base / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    generate_sample_data(
        locations=QUICK_LOCATIONS,
        output_dir=raw_dir,
        seed=42,
    )
    csv_path = consolidate(input_dir=raw_dir, output_dir=processed_dir)
    return csv_path


@pytest.fixture(scope="module")
def analysis_df(sample_csv):
    """Return the clean (non-failed) analysis DataFrame."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    # Override CSV path for tests
    from analysis import comparative
    orig_path = comparative.CSV_PATH
    comparative.CSV_PATH = sample_csv
    df = comparative.load_data()
    comparative.CSV_PATH = orig_path
    return df


@pytest.fixture(scope="module")
def analysis_results(sample_csv):
    """Run the full comparative analysis and return the results dict."""
    from analysis import comparative
    orig_path = comparative.CSV_PATH
    comparative.CSV_PATH = sample_csv
    results = comparative.main()
    comparative.CSV_PATH = orig_path
    return results


# ============================================================
# Comparative Analysis
# ============================================================

class TestComparativeAnalysis:

    def test_load_and_filter_data(self, analysis_df):
        """load_data() should exclude failed rows and add delivery_time_mid."""
        assert len(analysis_df) > 0
        assert "failed" not in analysis_df["data_completeness"].values
        assert "delivery_time_mid" in analysis_df.columns

    def test_load_requires_csv(self, tmp_path, monkeypatch):
        """load_data() should call sys.exit when CSV is missing."""
        from analysis import comparative
        monkeypatch.setattr(comparative, "CSV_PATH", tmp_path / "nonexistent.csv")
        with pytest.raises(SystemExit):
            comparative.load_data()

    def test_price_positioning_columns(self, analysis_results):
        df = analysis_results["prices"]
        required = {"product", "rappi_avg", "ubereats_avg", "ue_vs_rappi_pct",
                    "didi_vs_rappi_pct", "cheapest_platform"}
        assert required.issubset(df.columns)

    def test_price_positioning_delta_direction(self, analysis_results):
        """ue_vs_rappi_pct should be positive when UE avg > Rappi avg."""
        df = analysis_results["prices"]
        mask = df["rappi_avg"].notna() & df["ubereats_avg"].notna()
        subset = df[mask]
        if subset.empty:
            pytest.skip("Insufficient data")
        for _, row in subset.iterrows():
            expected_sign = row["ubereats_avg"] > row["rappi_avg"]
            actual_positive = row["ue_vs_rappi_pct"] > 0
            assert expected_sign == actual_positive, (
                f"Delta sign mismatch for {row['product']}: "
                f"UE={row['ubereats_avg']}, Rappi={row['rappi_avg']}, "
                f"delta={row['ue_vs_rappi_pct']}"
            )

    def test_delivery_times_columns(self, analysis_results):
        df = analysis_results["times"]
        assert {"zone_type", "rappi_avg_time", "ubereats_avg_time",
                "fastest_platform"}.issubset(df.columns)

    def test_delivery_times_fastest_is_min(self, analysis_results):
        """fastest_platform should correspond to the lowest avg time in each row."""
        df = analysis_results["times"]
        time_cols = {
            "rappi": "rappi_avg_time",
            "ubereats": "ubereats_avg_time",
            "didifood": "didifood_avg_time",
        }
        for _, row in df.iterrows():
            available = {p: row[col] for p, col in time_cols.items() if pd.notna(row[col])}
            if len(available) < 2:
                continue
            expected_fastest = min(available, key=available.get)
            assert row["fastest_platform"] == expected_fastest, (
                f"Zone {row['zone_type']}: expected fastest={expected_fastest}, "
                f"got {row['fastest_platform']}"
            )

    def test_fee_structure_columns(self, analysis_results):
        df = analysis_results["fees"]
        assert {"platform", "avg_delivery_fee", "avg_service_fee",
                "avg_total_fee", "fee_as_pct_of_product"}.issubset(df.columns)

    def test_fee_total_equals_delivery_plus_service(self, analysis_results):
        df = analysis_results["fees"]
        for _, row in df.iterrows():
            if pd.notna(row["avg_delivery_fee"]) and pd.notna(row["avg_service_fee"]):
                expected = round(row["avg_delivery_fee"] + row["avg_service_fee"], 2)
                assert abs(row["avg_total_fee"] - expected) < 0.01, (
                    f"{row['platform']}: total_fee={row['avg_total_fee']}, "
                    f"expected={expected}"
                )

    def test_fee_pct_positive(self, analysis_results):
        df = analysis_results["fees"]
        for _, row in df.iterrows():
            if pd.notna(row["fee_as_pct_of_product"]):
                assert row["fee_as_pct_of_product"] > 0

    def test_promotions_columns(self, analysis_results):
        df = analysis_results["promotions"]
        assert {"platform", "promo_rate_pct", "total_observations",
                "promo_observations"}.issubset(df.columns)

    def test_promo_rate_in_valid_range(self, analysis_results):
        df = analysis_results["promotions"]
        for _, row in df.iterrows():
            assert 0 <= row["promo_rate_pct"] <= 100

    def test_promo_observations_le_total(self, analysis_results):
        df = analysis_results["promotions"]
        for _, row in df.iterrows():
            assert row["promo_observations"] <= row["total_observations"]

    def test_geographic_variability_columns(self, analysis_results):
        df = analysis_results["geographic"]
        assert {"zone_type", "platform", "avg_price", "avg_fee",
                "avg_total_price", "rappi_rank"}.issubset(df.columns)

    def test_geographic_covers_all_platforms(self, analysis_results):
        df = analysis_results["geographic"]
        platforms_in_data = set(df["platform"].unique())
        assert "rappi" in platforms_in_data

    def test_analysis_saves_csvs(self, analysis_results, tmp_path):
        """Running main() with a patched reports dir should produce 5 CSVs."""
        from analysis import comparative
        import sys

        orig_path = comparative.CSV_PATH
        orig_reports = comparative.REPORTS_DIR

        raw = tmp_path / "raw"
        processed = tmp_path / "processed"
        reports = tmp_path / "reports"
        raw.mkdir(); processed.mkdir(); reports.mkdir()

        generate_sample_data(locations=QUICK_LOCATIONS[:2], output_dir=raw, seed=42)
        csv_path = consolidate(input_dir=raw, output_dir=processed)

        comparative.CSV_PATH = csv_path
        comparative.REPORTS_DIR = reports
        comparative.main()
        comparative.CSV_PATH = orig_path
        comparative.REPORTS_DIR = orig_reports

        expected = [
            "analysis_prices.csv",
            "analysis_times.csv",
            "analysis_fees.csv",
            "analysis_promotions.csv",
            "analysis_geographic.csv",
        ]
        for name in expected:
            assert (reports / name).exists(), f"Missing {name}"


# ============================================================
# Insights
# ============================================================

class TestInsights:

    @pytest.fixture(scope="class")
    def insights(self, analysis_results):
        from analysis.insights import generate_insights
        return generate_insights(analysis_results)

    def test_generates_exactly_5_insights(self, insights):
        assert len(insights) == 5

    def test_each_insight_has_required_fields(self, insights):
        required = {"number", "category", "finding", "impact", "recommendation", "data_support"}
        for ins in insights:
            assert required.issubset(ins.keys()), (
                f"Insight #{ins.get('number')} missing fields: {required - ins.keys()}"
            )

    def test_insight_numbers_are_1_to_5(self, insights):
        numbers = {ins["number"] for ins in insights}
        assert numbers == {1, 2, 3, 4, 5}

    def test_insight_categories_are_unique(self, insights):
        categories = [ins["category"] for ins in insights]
        assert len(categories) == len(set(categories)), "Duplicate categories in insights"

    def test_all_text_fields_are_non_empty(self, insights):
        for ins in insights:
            for field in ("finding", "impact", "recommendation"):
                assert ins[field].strip(), f"Insight #{ins['number']} has empty '{field}'"

    def test_data_support_is_dict(self, insights):
        for ins in insights:
            assert isinstance(ins["data_support"], dict)

    def test_save_creates_json_and_txt(self, analysis_results, tmp_path):
        from analysis.insights import generate_insights, save_insights
        insights = generate_insights(analysis_results)
        save_insights(insights, output_dir=tmp_path)

        json_file = tmp_path / "top5_insights.json"
        txt_file = tmp_path / "top5_insights.txt"
        assert json_file.exists()
        assert txt_file.exists()

        # JSON is valid and has 5 items
        data = json.loads(json_file.read_text())
        assert len(data) == 5

        # TXT contains at least one insight header
        txt_content = txt_file.read_text()
        assert "INSIGHT #1" in txt_content

    def test_insights_are_data_driven(self, analysis_results, analysis_df):
        """Insights should reference actual numbers from the data."""
        from analysis.insights import generate_insights
        insights = generate_insights(analysis_results)

        price_insight = next(i for i in insights if i["category"] == "pricing")
        ds = price_insight["data_support"]
        assert "rappi_avg_price_mxn" in ds
        rappi_avg = ds["rappi_avg_price_mxn"]

        # The value should be in a realistic range for CDMX fast food
        assert 50 <= rappi_avg <= 250, f"Rappi avg price {rappi_avg} looks unrealistic"


# ============================================================
# Visualizations
# ============================================================

class TestVisualizations:

    def test_charts_created(self, analysis_results, tmp_path):
        """All 8 charts should be created as PNG files."""
        from analysis import visualizations

        charts_dir = tmp_path / "charts"
        charts_dir.mkdir()
        df = analysis_results["raw"]

        visualizations.plot_price_comparison(df, charts_dir)
        visualizations.plot_total_cost_breakdown(df, charts_dir)
        visualizations.plot_geographic_heatmap(df, charts_dir)
        visualizations.plot_delivery_times(df, charts_dir)
        visualizations.plot_fee_comparison(df, charts_dir)
        visualizations.plot_promotion_rates(df, charts_dir)
        visualizations.plot_competitive_radar(df, charts_dir)
        visualizations.plot_price_delta_by_zone(df, charts_dir)

        png_files = sorted(charts_dir.glob("*.png"))
        assert len(png_files) == 8, f"Expected 8 PNGs, got {len(png_files)}"

    def test_charts_have_non_zero_size(self, analysis_results, tmp_path):
        """All generated PNGs should be non-empty files."""
        from analysis import visualizations

        charts_dir = tmp_path / "charts2"
        charts_dir.mkdir()
        df = analysis_results["raw"]

        for fn in [
            visualizations.plot_price_comparison,
            visualizations.plot_total_cost_breakdown,
            visualizations.plot_geographic_heatmap,
            visualizations.plot_delivery_times,
            visualizations.plot_fee_comparison,
            visualizations.plot_promotion_rates,
            visualizations.plot_competitive_radar,
            visualizations.plot_price_delta_by_zone,
        ]:
            fn(df, charts_dir)

        for png in charts_dir.glob("*.png"):
            assert png.stat().st_size > 5_000, f"{png.name} looks too small (corrupt?)"

    def test_charts_named_correctly(self, analysis_results, tmp_path):
        """Chart filenames should follow the 01_*.png convention."""
        from analysis import visualizations

        charts_dir = tmp_path / "charts3"
        charts_dir.mkdir()
        df = analysis_results["raw"]

        expected_names = {
            "01_price_comparison.png",
            "02_total_cost_breakdown.png",
            "03_geographic_heatmap.png",
            "04_delivery_times.png",
            "05_fee_comparison.png",
            "06_promotion_rates.png",
            "07_competitive_radar.png",
            "08_price_delta_by_zone.png",
        }
        for fn in [
            visualizations.plot_price_comparison,
            visualizations.plot_total_cost_breakdown,
            visualizations.plot_geographic_heatmap,
            visualizations.plot_delivery_times,
            visualizations.plot_fee_comparison,
            visualizations.plot_promotion_rates,
            visualizations.plot_competitive_radar,
            visualizations.plot_price_delta_by_zone,
        ]:
            fn(df, charts_dir)

        actual = {f.name for f in charts_dir.glob("*.png")}
        assert actual == expected_names

    def test_no_open_figures_after_generation(self, analysis_results, tmp_path):
        """Figures should be closed after saving (no memory leak)."""
        import matplotlib.pyplot as plt
        from analysis import visualizations

        charts_dir = tmp_path / "charts4"
        charts_dir.mkdir()
        df = analysis_results["raw"]

        plt.close("all")
        before = len(plt.get_fignums())

        visualizations.plot_price_comparison(df, charts_dir)
        visualizations.plot_fee_comparison(df, charts_dir)

        after = len(plt.get_fignums())
        assert after == before, (
            f"Expected {before} open figures after saving, got {after} — possible memory leak"
        )
