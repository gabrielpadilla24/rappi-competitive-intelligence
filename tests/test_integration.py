"""
Integration tests for the data pipeline.

Tests are self-contained: they generate data in a tmp_path fixture
and never touch the real data/ directory.
"""

import csv
import json
from pathlib import Path

import pytest

from config.locations import QUICK_LOCATIONS
from scripts.generate_sample_data import generate_sample_data
from scripts.consolidate_data import consolidate, flatten_result


# ============================================================
# Sample Data Generator
# ============================================================

class TestSampleDataGenerator:
    """Verify that synthetic data generation produces well-formed output."""

    def test_generate_creates_json_files(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS[:2],
            output_dir=tmp_path,
            seed=42,
        )
        assert len(files) > 0
        assert all(f.suffix == ".json" for f in files)
        assert all(f.exists() for f in files)

    def test_number_of_files_matches_expected(self, tmp_path):
        # 2 locations × 3 platforms × 2 restaurants = 12 files
        files = generate_sample_data(
            locations=QUICK_LOCATIONS[:2],
            output_dir=tmp_path,
            seed=42,
        )
        assert len(files) == 12

    def test_generated_json_has_required_fields(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS[:1],
            output_dir=tmp_path,
            seed=42,
        )
        required_fields = {
            "scrape_id", "timestamp", "platform", "location_id",
            "data_completeness", "errors",
        }
        for filepath in files:
            data = json.loads(filepath.read_text())
            for field in required_fields:
                assert field in data, f"Missing field '{field}' in {filepath.name}"

    def test_prices_in_realistic_range(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS,
            output_dir=tmp_path,
            seed=42,
        )
        for filepath in files:
            data = json.loads(filepath.read_text())
            for product in data.get("products", []):
                price = product.get("price_mxn")
                if price is not None:
                    assert 50 <= price <= 300, (
                        f"Price {price} out of expected range in {filepath.name}"
                    )

    def test_output_covers_all_platforms(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS[:1],
            output_dir=tmp_path,
            seed=42,
        )
        platforms = set()
        for filepath in files:
            data = json.loads(filepath.read_text())
            platforms.add(data["platform"])
        assert platforms == {"rappi", "ubereats", "didifood"}

    def test_didifood_has_failures(self, tmp_path):
        # Use enough locations that ~30% failure rate is visible
        files = generate_sample_data(
            locations=QUICK_LOCATIONS,
            output_dir=tmp_path,
            seed=42,
        )
        didi_results = [
            json.loads(f.read_text())
            for f in files
            if json.loads(f.read_text()).get("platform") == "didifood"
        ]
        failed = [r for r in didi_results if r["data_completeness"] == "failed"]
        # With seed=42 and enough samples, at least 1 DiDi failure should exist
        assert len(failed) >= 1, "Expected at least one DiDi Food failure"

    def test_didifood_never_full_completeness(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS,
            output_dir=tmp_path,
            seed=42,
        )
        for filepath in files:
            data = json.loads(filepath.read_text())
            if data["platform"] == "didifood":
                assert data["data_completeness"] in ("partial", "failed"), (
                    f"DiDi Food should never be 'full', got '{data['data_completeness']}'"
                )

    def test_clean_flag_removes_existing_files(self, tmp_path):
        # Create a sentinel file
        sentinel = tmp_path / "old_data.json"
        sentinel.write_text("{}")
        assert sentinel.exists()

        generate_sample_data(locations=QUICK_LOCATIONS[:1], output_dir=tmp_path, clean=True)
        # Sentinel should be gone
        assert not sentinel.exists()

    def test_reproducibility_with_same_seed(self, tmp_path):
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"
        dir_a.mkdir()
        dir_b.mkdir()

        files_a = generate_sample_data(locations=QUICK_LOCATIONS[:1], output_dir=dir_a, seed=42)
        files_b = generate_sample_data(locations=QUICK_LOCATIONS[:1], output_dir=dir_b, seed=42)

        assert len(files_a) == len(files_b)
        for fa, fb in zip(sorted(files_a), sorted(files_b)):
            data_a = json.loads(fa.read_text())
            data_b = json.loads(fb.read_text())
            # Prices should be identical between runs with same seed
            assert data_a.get("products") == data_b.get("products"), (
                "Same seed should produce same product prices"
            )

    def test_delivery_info_present_for_non_failed(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS[:2],
            output_dir=tmp_path,
            seed=42,
        )
        for filepath in files:
            data = json.loads(filepath.read_text())
            if data["data_completeness"] != "failed":
                assert data.get("delivery") is not None, (
                    f"Non-failed result should have delivery info: {filepath.name}"
                )

    def test_ratings_in_valid_range(self, tmp_path):
        files = generate_sample_data(
            locations=QUICK_LOCATIONS[:2],
            output_dir=tmp_path,
            seed=42,
        )
        for filepath in files:
            data = json.loads(filepath.read_text())
            restaurant = data.get("restaurant") or {}
            rating = restaurant.get("rating")
            if rating is not None:
                assert 1.0 <= rating <= 5.0, f"Rating {rating} out of range"


# ============================================================
# Consolidator
# ============================================================

class TestConsolidator:
    """Verify that consolidation produces a valid, well-structured CSV."""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Generate a small sample dataset and return the directory."""
        generate_sample_data(
            locations=QUICK_LOCATIONS[:2],
            output_dir=tmp_path / "raw",
            seed=42,
        )
        return tmp_path / "raw"

    def test_consolidate_creates_csv(self, sample_dir, tmp_path):
        out_dir = tmp_path / "processed"
        csv_path = consolidate(input_dir=sample_dir, output_dir=out_dir)
        assert csv_path.exists()
        assert csv_path.suffix == ".csv"

    def test_csv_has_expected_columns(self, sample_dir, tmp_path):
        from scripts.consolidate_data import CSV_COLUMNS
        out_dir = tmp_path / "processed"
        csv_path = consolidate(input_dir=sample_dir, output_dir=out_dir)

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            actual_columns = set(reader.fieldnames or [])

        for col in CSV_COLUMNS:
            assert col in actual_columns, f"Missing column '{col}' in CSV"

    def test_csv_one_row_per_product(self, sample_dir, tmp_path):
        out_dir = tmp_path / "processed"
        csv_path = consolidate(input_dir=sample_dir, output_dir=out_dir)

        # Count total products across all JSONs
        total_products = 0
        for filepath in sample_dir.glob("*.json"):
            data = json.loads(filepath.read_text())
            products = data.get("products") or []
            total_products += max(1, len(products))  # at least 1 row per result

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == total_products

    def test_csv_total_price_calculated(self, sample_dir, tmp_path):
        out_dir = tmp_path / "processed"
        csv_path = consolidate(input_dir=sample_dir, output_dir=out_dir)

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        checked = 0
        for row in rows:
            price = row.get("product_price_mxn")
            fee = row.get("delivery_fee_mxn")
            total = row.get("total_price_mxn")

            if price and fee and total:
                p = float(price)
                d = float(fee)
                svc = float(row.get("service_fee_mxn") or 0)
                expected = round(p + d + svc, 2)
                assert abs(float(total) - expected) < 0.01, (
                    f"total_price mismatch: {float(total)} != {expected}"
                )
                checked += 1

        assert checked > 0, "No rows with complete price data to verify"

    def test_csv_handles_corrupt_json(self, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        # Write a valid file
        generate_sample_data(locations=QUICK_LOCATIONS[:1], output_dir=raw_dir, seed=42)

        # Inject a corrupt JSON
        (raw_dir / "corrupt.json").write_text("{ this is not valid json }")

        out_dir = tmp_path / "processed"
        # Should complete without raising an exception
        csv_path = consolidate(input_dir=raw_dir, output_dir=out_dir)
        assert csv_path.exists()

        # The valid rows should still be in the CSV
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0

    def test_csv_empty_input_dir(self, tmp_path):
        raw_dir = tmp_path / "empty_raw"
        raw_dir.mkdir()
        out_dir = tmp_path / "processed"

        # Should not raise, just return the (possibly empty) output path
        csv_path = consolidate(input_dir=raw_dir, output_dir=out_dir)
        assert isinstance(csv_path, Path)

    def test_flatten_result_no_products(self):
        """A result with no products should produce exactly one row."""
        data = {
            "scrape_id": "test-123",
            "timestamp": "2025-01-01T00:00:00",
            "platform": "rappi",
            "location_id": "polanco",
            "location_address": "Masaryk 340",
            "location_lat": 19.43,
            "location_lng": -99.19,
            "zone_type": "high_income",
            "zone_label": "Polanco",
            "city": "CDMX",
            "restaurant": {"name": "McDonald's", "available": True},
            "delivery": {"fee_mxn": 29.0, "service_fee_mxn": 15.0},
            "products": [],
            "promotions": [],
            "errors": [],
            "data_completeness": "failed",
            "scrape_duration_seconds": 12.5,
        }
        rows = flatten_result(data)
        assert len(rows) == 1
        assert rows[0]["product_name"] == ""

    def test_flatten_result_multiple_products(self):
        """A result with 3 products should produce 3 rows."""
        data = {
            "scrape_id": "test-456",
            "timestamp": "2025-01-01T00:00:00",
            "platform": "ubereats",
            "location_id": "condesa",
            "location_address": "Amsterdam 240",
            "location_lat": 19.41,
            "location_lng": -99.17,
            "zone_type": "high_income",
            "zone_label": "Condesa",
            "city": "CDMX",
            "restaurant": {"name": "Burger King", "available": True, "rating": 4.2},
            "delivery": {"fee_mxn": 25.0, "service_fee_mxn": 18.0},
            "products": [
                {"name": "Whopper", "reference_id": "whopper", "price_mxn": 109.0, "available": True},
                {"name": "Combo Whopper", "reference_id": "combo_whopper", "price_mxn": 169.0, "available": True},
                {"name": "Papas", "reference_id": "fries", "price_mxn": 45.0, "available": True},
            ],
            "promotions": [{"type": "discount", "description": "20% OFF", "value": "20%"}],
            "errors": [],
            "data_completeness": "full",
            "scrape_duration_seconds": 22.1,
        }
        rows = flatten_result(data)
        assert len(rows) == 3
        # All rows share the same delivery fee
        for row in rows:
            assert row["delivery_fee_mxn"] == 25.0
        # Total price calculated correctly for first product
        assert rows[0]["total_price_mxn"] == round(109.0 + 25.0 + 18.0, 2)
        # Promotions concatenated
        assert rows[0]["promotions_description"] == "20% OFF"
        assert rows[0]["promotions_count"] == 1
