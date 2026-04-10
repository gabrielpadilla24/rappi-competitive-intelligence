"""
Base scraper class defining the interface for all platform scrapers.
Implements the Strategy pattern — each platform extends this class.
"""

import json
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from config.settings import RAW_DIR, SCREENSHOTS_DIR, TAKE_SCREENSHOTS
from config.locations import Location
from config.products import Product, TargetRestaurant


# ============================================================
# Data Models (normalized schema)
# ============================================================

@dataclass
class ProductResult:
    """Price and availability data for a single product."""
    name: str
    reference_id: str
    price_mxn: Optional[float] = None
    available: bool = True
    description: str = ""
    original_name: str = ""  # Name as shown on the platform


@dataclass
class DeliveryInfo:
    """Delivery fees and timing for a restaurant."""
    fee_mxn: Optional[float] = None
    service_fee_mxn: Optional[float] = None
    estimated_time_min: Optional[int] = None
    estimated_time_max: Optional[int] = None
    free_delivery_threshold_mxn: Optional[float] = None
    surge_active: bool = False


@dataclass
class PromotionInfo:
    """A promotion or discount offered by the platform."""
    type: str = ""         # discount, free_delivery, bundle, cashback
    description: str = ""
    value: str = ""        # "50%", "$30 off", "2x1"
    conditions: str = ""


@dataclass
class RestaurantResult:
    """Data collected for a single restaurant on a single platform."""
    name: str
    platform_id: str = ""
    available: bool = True
    rating: Optional[float] = None
    review_count: Optional[int] = None


@dataclass
class ScrapeResult:
    """Complete result for one observation (1 location × 1 platform × 1 restaurant)."""
    scrape_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    platform: str = ""
    location_id: str = ""
    location_address: str = ""
    location_lat: float = 0.0
    location_lng: float = 0.0
    zone_type: str = ""
    zone_label: str = ""
    city: str = ""
    restaurant: Optional[RestaurantResult] = None
    products: list[ProductResult] = field(default_factory=list)
    delivery: Optional[DeliveryInfo] = None
    promotions: list[PromotionInfo] = field(default_factory=list)
    screenshot_path: str = ""
    errors: list[str] = field(default_factory=list)
    data_completeness: str = "full"  # full, partial, failed
    scrape_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        return d

    def save(self, directory: Path = RAW_DIR) -> Path:
        """Save result as JSON file."""
        filename = f"{self.platform}_{self.location_id}_{self.restaurant.name if self.restaurant else 'unknown'}_{self.scrape_id[:8]}.json"
        # Sanitize filename
        filename = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)
        filepath = directory / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return filepath


# ============================================================
# Base Scraper Class
# ============================================================

class BaseScraper(ABC):
    """
    Abstract base class for all platform scrapers.

    Each platform (Rappi, Uber Eats, DiDi Food) implements this interface.
    The scraper handles browser setup, location setting, restaurant search,
    and data extraction.
    """

    def __init__(self, platform_name: str):
        self.platform = platform_name
        self.logger = logging.getLogger(f"scraper.{platform_name}")
        self.browser = None
        self.context = None
        self.page = None

    # ----- Lifecycle -----

    @abstractmethod
    async def setup(self) -> None:
        """Initialize browser and any platform-specific setup."""
        pass

    @abstractmethod
    async def teardown(self) -> None:
        """Close browser and clean up resources."""
        pass

    # ----- Core scraping methods -----

    @abstractmethod
    async def set_location(self, location: Location) -> bool:
        """
        Set the delivery address on the platform.
        Returns True if location was set successfully.
        """
        pass

    @abstractmethod
    async def search_restaurant(self, restaurant: TargetRestaurant) -> Optional[RestaurantResult]:
        """
        Search for a specific restaurant at the current location.
        Returns RestaurantResult if found, None if not available.
        """
        pass

    @abstractmethod
    async def get_delivery_info(self) -> Optional[DeliveryInfo]:
        """
        Extract delivery fee, service fee, and estimated time
        from the current restaurant page.
        """
        pass

    @abstractmethod
    async def get_product_price(self, product: Product) -> Optional[ProductResult]:
        """
        Search for a specific product in the current restaurant's menu
        and extract its price.
        """
        pass

    @abstractmethod
    async def get_promotions(self) -> list[PromotionInfo]:
        """
        Extract visible promotions/discounts on the current page.
        """
        pass

    # ----- High-level orchestration -----

    async def scrape_restaurant_at_location(
        self,
        location: Location,
        restaurant: TargetRestaurant,
        products: list[Product],
    ) -> ScrapeResult:
        """
        Full scrape pipeline for one restaurant at one location.
        This is the main entry point called by the runner.
        """
        import time
        start_time = time.time()

        result = ScrapeResult(
            platform=self.platform,
            location_id=location.id,
            location_address=location.address,
            location_lat=location.lat,
            location_lng=location.lng,
            zone_type=location.zone_type,
            zone_label=location.zone_label,
            city=location.city,
        )

        try:
            # Step 1: Set location
            self.logger.info(f"Setting location: {location.short_name}")
            location_set = await self.set_location(location)
            if not location_set:
                result.errors.append("Failed to set location")
                result.data_completeness = "failed"
                return result

            # Step 2: Search restaurant
            self.logger.info(f"Searching for: {restaurant.name}")
            rest_result = await self.search_restaurant(restaurant)
            if not rest_result:
                result.restaurant = RestaurantResult(
                    name=restaurant.name, available=False
                )
                result.errors.append(f"Restaurant '{restaurant.name}' not found")
                result.data_completeness = "failed"
                return result

            result.restaurant = rest_result

            # Step 3: Get delivery info
            self.logger.info("Extracting delivery info")
            delivery = await self.get_delivery_info()
            if delivery:
                result.delivery = delivery
            else:
                result.errors.append("Could not extract delivery info")

            # Step 4: Get product prices
            for product in products:
                self.logger.info(f"Looking for product: {product.name}")
                prod_result = await self.get_product_price(product)
                if prod_result:
                    result.products.append(prod_result)
                else:
                    result.products.append(ProductResult(
                        name=product.name,
                        reference_id=product.id,
                        available=False,
                    ))
                    result.errors.append(f"Product '{product.name}' not found")

            # Step 5: Get promotions
            self.logger.info("Extracting promotions")
            promos = await self.get_promotions()
            result.promotions = promos

            # Step 6: Screenshot
            if TAKE_SCREENSHOTS and self.page:
                screenshot_path = await self.take_screenshot(location, restaurant)
                result.screenshot_path = str(screenshot_path)

            # Determine completeness
            if result.errors:
                result.data_completeness = "partial"
            if not result.products or all(not p.available for p in result.products):
                result.data_completeness = "failed"

        except Exception as e:
            self.logger.error(f"Scrape failed: {e}", exc_info=True)
            result.errors.append(f"Exception: {str(e)}")
            result.data_completeness = "failed"

        result.scrape_duration_seconds = round(time.time() - start_time, 2)
        return result

    # ----- Utilities -----

    async def take_screenshot(self, location: Location, restaurant: TargetRestaurant) -> Path:
        """Take a screenshot of the current page as evidence."""
        platform_dir = SCREENSHOTS_DIR / self.platform
        platform_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{location.id}_{restaurant.id}_{timestamp}.png"
        filepath = platform_dir / filename

        if self.page:
            await self.page.screenshot(path=str(filepath), full_page=False)
            self.logger.info(f"Screenshot saved: {filepath}")

        return filepath

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} platform='{self.platform}'>"
