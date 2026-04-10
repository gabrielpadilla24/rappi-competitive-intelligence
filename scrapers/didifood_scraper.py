"""
DiDi Food scraper implementation.
Scrapes restaurant data from DiDi Food in Mexico.

NOTE: DiDi Food is primarily mobile-only. This scraper may have
limited data compared to Rappi and Uber Eats. Limitations will be
documented transparently.

TODO: Implement in Phase 3
"""

from typing import Optional
from scrapers.base import (
    BaseScraper, RestaurantResult, DeliveryInfo,
    ProductResult, PromotionInfo,
)
from config.locations import Location
from config.products import Product, TargetRestaurant


class DidiFloodScraper(BaseScraper):
    """Scraper for DiDi Food Mexico."""

    def __init__(self):
        super().__init__(platform_name="didifood")

    async def setup(self) -> None:
        """Initialize browser — may need mobile emulation."""
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
