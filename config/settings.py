"""
Global configuration for the Competitive Intelligence System.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
REPORTS_DIR = BASE_DIR / "reports"

# Create directories if they don't exist
for d in [RAW_DIR, PROCESSED_DIR, SCREENSHOTS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# Scraping Settings
# ============================================================

# Rate limiting
MIN_DELAY_SECONDS = 3        # Minimum delay between requests
MAX_DELAY_SECONDS = 6        # Maximum delay between requests
DELAY_BETWEEN_LOCATIONS = 8  # Delay between different locations
DELAY_BETWEEN_PLATFORMS = 2  # Delay between different platforms

# Retry logic
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5  # seconds: 5, 10, 20, 40...

# Timeouts
PAGE_LOAD_TIMEOUT = 30000   # 30 seconds in ms
NAVIGATION_TIMEOUT = 30000  # 30 seconds in ms
ELEMENT_TIMEOUT = 10000     # 10 seconds in ms

# Browser settings
HEADLESS = True  # Set to False for debugging
VIEWPORT_WIDTH = 1366
VIEWPORT_HEIGHT = 768

# Screenshots
TAKE_SCREENSHOTS = True
SCREENSHOT_QUALITY = 80  # JPEG quality

# ============================================================
# Platform URLs (Mexico)
# ============================================================

PLATFORM_URLS = {
    "rappi": {
        "base": "https://www.rappi.com.mx",
        "restaurants": "https://www.rappi.com.mx/restaurantes",
    },
    "ubereats": {
        "base": "https://www.ubereats.com",
        "feed": "https://www.ubereats.com/mx/feed",
    },
    "didifood": {
        "base": "https://web.didiglobal.com/mx/food/",
    },
}

# ============================================================
# Platforms to scrape
# ============================================================

ACTIVE_PLATFORMS = ["rappi", "ubereats", "didifood"]

# ============================================================
# API Keys (optional)
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PROXY_URL = os.getenv("PROXY_URL", "")

# ============================================================
# User Agents Pool
# ============================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# ============================================================
# Analysis Settings
# ============================================================

# Currency
CURRENCY = "MXN"
CURRENCY_SYMBOL = "$"

# Zone types for analysis grouping
ZONE_TYPES = [
    "high_income",
    "medium_high_income",
    "medium_income",
    "low_income",
    "commercial",
]

# Visualization
CHART_STYLE = "seaborn-v0_8-whitegrid"
CHART_DPI = 150
CHART_FIGSIZE = (12, 6)

# Platform colors for consistent charting
PLATFORM_COLORS = {
    "rappi": "#FF441F",      # Rappi orange-red
    "ubereats": "#06C167",   # Uber Eats green
    "didifood": "#FF8C00",   # DiDi Food orange
}

PLATFORM_LABELS = {
    "rappi": "Rappi",
    "ubereats": "Uber Eats",
    "didifood": "DiDi Food",
}
