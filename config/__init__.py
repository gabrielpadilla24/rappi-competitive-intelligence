"""Configuration package for Competitive Intelligence System."""

from .settings import *
from .locations import LOCATIONS, Location, get_quick_locations, get_location_by_id
from .products import (
    PRODUCTS, Product, TARGET_RESTAURANTS, TargetRestaurant,
    get_products_by_priority, get_restaurants_by_priority, get_product_by_id,
)
