"""
Uber Eats scraper implementation.
Scrapes restaurant data from ubereats.com/mx using Playwright.

TODO: Implement in Phase 3
"""

from typing import Optional
from scrapers.base import (
    BaseScraper, RestaurantResult, DeliveryInfo,
    ProductResult, PromotionInfo,
)
from config.locations import Location
from config.products import Product, TargetRestaurant


class UberEatsScraper(BaseScraper):
    """Scraper for Uber Eats Mexico (ubereats.com/mx)."""

    def __init__(self):
        super().__init__(platform_name="ubereats")

    async def setup(self) -> None:
        """Initialize Playwright browser with stealth mode."""
        raise NotImplementedError("Phase 3")

    async def teardown(self) -> None:
        raise NotImplementedError("Phase 3")

    async def set_location(self, location: Location) -> bool:
        raise NotImplementedError("Phase 3")

    async def search_restaurant(self, restaurant: TargetRestaurant) -> Optional[RestaurantResult]:
        raise NotImplementedError("Phase 3")

    async def get_delivery_info(self) -> Optional[DeliveryInfo]:
        raise NotImplementedError("Phase 3")

    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        raise NotImplementedError("Phase 3")

    async def get_promotions(self) -> list[PromotionInfo]:
        raise NotImplementedError("Phase 3")
