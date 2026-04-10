"""
Tests for scraper modules.
"""

import pytest
from scrapers.utils.parsers import parse_price, parse_time_range, fuzzy_match
from config.locations import (
    LOCATIONS, QUICK_LOCATIONS, FULL_LOCATIONS,
    get_locations_by_zone, get_location_by_id, get_quick_locations,
)
from config.products import (
    PRODUCTS, TARGET_RESTAURANTS, PRIORITY_RESTAURANTS,
    get_products_by_restaurant, get_product_by_id,
)
from scrapers.base import (
    ScrapeResult, ProductResult, DeliveryInfo,
    PromotionInfo, RestaurantResult,
)


# ============================================================
# Config Tests
# ============================================================

class TestLocations:
    def test_total_locations(self):
        assert len(LOCATIONS) == 25

    def test_quick_locations_are_priority_1(self):
        quick = get_quick_locations()
        assert all(loc.priority == 1 for loc in quick)
        assert len(quick) >= 5  # at least 5 priority-1 locations

    def test_full_locations_exclude_secondary_cities(self):
        assert all(loc.priority <= 2 for loc in FULL_LOCATIONS)
        assert len(FULL_LOCATIONS) == 23  # 25 - 2 secondary

    def test_zone_types_covered(self):
        zone_types = set(loc.zone_type for loc in LOCATIONS)
        expected = {"high_income", "medium_high_income", "medium_income", "low_income", "commercial"}
        assert zone_types == expected

    def test_get_location_by_id(self):
        loc = get_location_by_id("polanco")
        assert loc is not None
        assert loc.colonia == "Polanco V Sección"
        assert loc.lat > 0

    def test_get_location_by_id_missing(self):
        assert get_location_by_id("nonexistent") is None

    def test_all_locations_have_coordinates(self):
        for loc in LOCATIONS:
            assert loc.lat != 0, f"Location {loc.id} has lat=0"
            assert loc.lng != 0, f"Location {loc.id} has lng=0"

    def test_high_income_locations(self):
        high = get_locations_by_zone("high_income")
        assert len(high) == 5


class TestProducts:
    def test_total_products(self):
        assert len(PRODUCTS) == 7

    def test_priority_products(self):
        priority = [p for p in PRODUCTS if p.priority == 1]
        assert len(priority) == 3  # Big Mac, Combo Big Mac, Whopper

    def test_target_restaurants(self):
        assert len(TARGET_RESTAURANTS) == 3  # McDonald's, BK, OXXO

    def test_priority_restaurants(self):
        assert len(PRIORITY_RESTAURANTS) == 2  # McDonald's, BK

    def test_get_products_by_restaurant(self):
        mcdonalds_products = get_products_by_restaurant("mcdonalds")
        assert len(mcdonalds_products) == 3
        product_ids = [p.id for p in mcdonalds_products]
        assert "big_mac" in product_ids

    def test_get_product_by_id(self):
        product = get_product_by_id("big_mac")
        assert product is not None
        assert product.restaurant == "McDonald's"

    def test_all_products_have_search_terms(self):
        for p in PRODUCTS:
            assert len(p.search_terms) > 0, f"Product {p.id} has no search terms"


# ============================================================
# Data Model Tests
# ============================================================

class TestDataModels:
    def test_scrape_result_creation(self):
        result = ScrapeResult(
            platform="rappi",
            location_id="polanco",
            location_address="Av. Masaryk 340",
            location_lat=19.4326,
            location_lng=-99.1942,
            zone_type="high_income",
            zone_label="Polanco",
            city="CDMX",
        )
        assert result.scrape_id  # UUID generated
        assert result.timestamp  # Timestamp generated
        assert result.platform == "rappi"
        assert result.data_completeness == "full"

    def test_scrape_result_to_dict(self):
        result = ScrapeResult(platform="ubereats", location_id="condesa")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["platform"] == "ubereats"
        assert d["location_id"] == "condesa"

    def test_product_result(self):
        pr = ProductResult(
            name="Big Mac",
            reference_id="big_mac",
            price_mxn=89.0,
            available=True,
        )
        assert pr.price_mxn == 89.0
        assert pr.available is True

    def test_delivery_info(self):
        di = DeliveryInfo(
            fee_mxn=29.0,
            service_fee_mxn=15.0,
            estimated_time_min=25,
            estimated_time_max=35,
        )
        assert di.fee_mxn == 29.0
        assert di.surge_active is False

    def test_promotion_info(self):
        pi = PromotionInfo(
            type="discount",
            description="2x1 en combos",
            value="50%",
        )
        assert pi.type == "discount"

    def test_scrape_result_with_full_data(self):
        result = ScrapeResult(
            platform="rappi",
            location_id="polanco",
            restaurant=RestaurantResult(
                name="McDonald's Polanco",
                available=True,
                rating=4.5,
            ),
            products=[
                ProductResult(name="Big Mac", reference_id="big_mac", price_mxn=89.0),
                ProductResult(name="Combo Big Mac", reference_id="combo_big_mac", price_mxn=149.0),
            ],
            delivery=DeliveryInfo(fee_mxn=29.0, service_fee_mxn=15.0),
            promotions=[
                PromotionInfo(type="discount", description="2x1", value="50%"),
            ],
        )
        d = result.to_dict()
        assert len(d["products"]) == 2
        assert d["restaurant"]["name"] == "McDonald's Polanco"
        assert d["delivery"]["fee_mxn"] == 29.0
        assert len(d["promotions"]) == 1


# ============================================================
# Parser Tests
# ============================================================

class TestParsers:
    def test_parse_price_basic(self):
        assert parse_price("$89.00") == 89.0

    def test_parse_price_no_cents(self):
        assert parse_price("$89") == 89.0

    def test_parse_price_comma_thousands(self):
        assert parse_price("$1,299.00") == 1299.0

    def test_parse_price_mxn_prefix(self):
        assert parse_price("MXN 89") == 89.0

    def test_parse_price_no_symbol(self):
        assert parse_price("89.00") == 89.0

    def test_parse_price_empty(self):
        assert parse_price("") is None

    def test_parse_price_non_numeric(self):
        assert parse_price("gratis") is None

    def test_parse_price_none_input(self):
        assert parse_price(None) is None

    def test_parse_price_zero(self):
        # Zero is not a valid price
        assert parse_price("$0") is None

    def test_parse_time_range_em_dash(self):
        assert parse_time_range("25–35 min") == (25, 35)

    def test_parse_time_range_hyphen(self):
        assert parse_time_range("25-35 min") == (25, 35)

    def test_parse_time_range_single(self):
        assert parse_time_range("30 min") == (30, 30)

    def test_parse_time_range_empty(self):
        assert parse_time_range("") == (None, None)

    def test_parse_time_range_no_match(self):
        assert parse_time_range("sin tiempo") == (None, None)

    def test_fuzzy_match_hit(self):
        assert fuzzy_match(["Big Mac", "BigMac"], "Big Mac Individual") is True

    def test_fuzzy_match_case_insensitive(self):
        assert fuzzy_match(["big mac"], "BIG MAC COMBO") is True

    def test_fuzzy_match_miss(self):
        assert fuzzy_match(["Big Mac"], "Whopper") is False

    def test_fuzzy_match_partial_term(self):
        assert fuzzy_match(["McNuggets"], "Chicken McNuggets 10 piezas") is True
