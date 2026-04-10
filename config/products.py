"""
Reference products for competitive price comparison.
Standardized items available across all platforms and zones.
"""

from dataclasses import dataclass


@dataclass
class Product:
    """A reference product to search for across platforms."""
    id: str
    name: str
    restaurant: str
    category: str        # fast_food, retail
    search_terms: list[str]  # Alternative names to search for
    description: str
    priority: int        # 1 = always, 2 = if time allows

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.restaurant})"


# ============================================================
# Reference Products
# ============================================================

PRODUCTS: list[Product] = [
    # ----- FAST FOOD — McDonald's -----
    Product(
        id="big_mac",
        name="Big Mac",
        restaurant="McDonald's",
        category="fast_food",
        search_terms=["Big Mac", "BigMac", "big mac"],
        description="Hamburguesa doble con salsa especial, lechuga, queso, pepinillos, cebolla en pan con ajonjolí",
        priority=1,
    ),
    Product(
        id="combo_big_mac",
        name="Combo Big Mac Mediano",
        restaurant="McDonald's",
        category="fast_food",
        search_terms=[
            "Combo Big Mac", "McCombo Big Mac", "Big Mac Combo",
            "Big Mac Mediano", "McCombo Big Mac Mediano",
        ],
        description="Big Mac + Papas Medianas + Bebida Mediana",
        priority=1,
    ),
    Product(
        id="mcnuggets_10",
        name="McNuggets 10 piezas",
        restaurant="McDonald's",
        category="fast_food",
        search_terms=[
            "McNuggets 10", "Chicken McNuggets 10",
            "McNuggets", "10 McNuggets", "10 Nuggets",
        ],
        description="10 piezas de pollo empanizado McNuggets",
        priority=2,
    ),

    # ----- FAST FOOD — Burger King -----
    Product(
        id="whopper",
        name="Whopper",
        restaurant="Burger King",
        category="fast_food",
        search_terms=["Whopper", "Whopper Jr", "WHOPPER"],
        description="Hamburguesa a la parrilla con tomate, lechuga, cebolla, pepinillos, ketchup y mayonesa",
        priority=1,
    ),
    Product(
        id="combo_whopper",
        name="Combo Whopper Mediano",
        restaurant="Burger King",
        category="fast_food",
        search_terms=[
            "Combo Whopper", "Whopper Combo", "Combo Whopper Mediano",
            "Whopper Mediano",
        ],
        description="Whopper + Papas Medianas + Bebida Mediana",
        priority=2,
    ),

    # ----- RETAIL / CONVENIENCE -----
    Product(
        id="coca_cola_500",
        name="Coca-Cola 500ml",
        restaurant="OXXO",  # or any convenience store
        category="retail",
        search_terms=[
            "Coca-Cola 500", "Coca Cola 500ml", "Coca-Cola",
            "Coca 500", "Refresco Coca-Cola",
        ],
        description="Coca-Cola Original 500ml botella PET",
        priority=2,
    ),
    Product(
        id="agua_bonafont_1l",
        name="Agua Bonafont 1L",
        restaurant="OXXO",
        category="retail",
        search_terms=[
            "Bonafont 1L", "Agua Bonafont", "Bonafont 1 Litro",
            "Agua Natural 1L",
        ],
        description="Agua natural Bonafont 1 litro",
        priority=2,
    ),
]


# ============================================================
# Target Restaurants
# ============================================================

@dataclass
class TargetRestaurant:
    """A restaurant chain to search for across platforms."""
    id: str
    name: str
    search_terms: list[str]
    category: str
    products: list[str]  # Product IDs to look for in this restaurant
    priority: int

TARGET_RESTAURANTS: list[TargetRestaurant] = [
    TargetRestaurant(
        id="mcdonalds",
        name="McDonald's",
        search_terms=["McDonald's", "McDonalds", "Mc Donald's", "mcdonald"],
        category="fast_food",
        products=["big_mac", "combo_big_mac", "mcnuggets_10"],
        priority=1,
    ),
    TargetRestaurant(
        id="burger_king",
        name="Burger King",
        search_terms=["Burger King", "BurgerKing", "BK", "burger king"],
        category="fast_food",
        products=["whopper", "combo_whopper"],
        priority=1,
    ),
    TargetRestaurant(
        id="oxxo",
        name="OXXO",
        search_terms=["OXXO", "Oxxo"],
        category="retail",
        products=["coca_cola_500", "agua_bonafont_1l"],
        priority=2,
    ),
]


# ============================================================
# Helper functions
# ============================================================

def get_products_by_priority(max_priority: int = 1) -> list[Product]:
    """Get products up to a given priority level."""
    return [p for p in PRODUCTS if p.priority <= max_priority]


def get_products_by_restaurant(restaurant_id: str) -> list[Product]:
    """Get products for a specific restaurant."""
    for r in TARGET_RESTAURANTS:
        if r.id == restaurant_id:
            return [p for p in PRODUCTS if p.id in r.products]
    return []


def get_restaurants_by_priority(max_priority: int = 1) -> list[TargetRestaurant]:
    """Get restaurants up to a given priority level."""
    return [r for r in TARGET_RESTAURANTS if r.priority <= max_priority]


def get_product_by_id(product_id: str) -> Product | None:
    """Get a single product by its ID."""
    for p in PRODUCTS:
        if p.id == product_id:
            return p
    return None


# Quick access
PRIORITY_PRODUCTS = get_products_by_priority(1)     # 4 core products
ALL_PRODUCTS = PRODUCTS                              # 7 products
PRIORITY_RESTAURANTS = get_restaurants_by_priority(1) # McDonald's + BK
ALL_RESTAURANTS = TARGET_RESTAURANTS                   # + OXXO
