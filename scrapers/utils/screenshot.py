"""
Screenshot utility for capturing evidence during scraping.
"""

import logging
from datetime import datetime
from pathlib import Path

from config.settings import SCREENSHOTS_DIR, SCREENSHOT_QUALITY

logger = logging.getLogger("scraper.screenshot")


async def capture_evidence(
    page,
    platform: str,
    location_id: str,
    restaurant_id: str,
    label: str = "",
    full_page: bool = False,
) -> Path:
    """
    Capture a screenshot as evidence of scraped data.

    Args:
        page: Playwright page object
        platform: Platform name (rappi, ubereats, didifood)
        location_id: Location identifier
        restaurant_id: Restaurant identifier
        label: Optional label for the screenshot
        full_page: Whether to capture full page or viewport only

    Returns:
        Path to the saved screenshot
    """
    platform_dir = SCREENSHOTS_DIR / platform
    platform_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [location_id, restaurant_id]
    if label:
        parts.append(label)
    parts.append(timestamp)

    filename = "_".join(parts) + ".png"
    filepath = platform_dir / filename

    try:
        await page.screenshot(
            path=str(filepath),
            full_page=full_page,
            type="png",
        )
        logger.info(f"Screenshot saved: {filepath.name}")
        return filepath
    except Exception as e:
        logger.warning(f"Screenshot failed: {e}")
        return Path("")


async def capture_element(
    page,
    selector: str,
    platform: str,
    location_id: str,
    label: str,
) -> Path:
    """
    Capture a screenshot of a specific element.

    Args:
        page: Playwright page object
        selector: CSS selector for the element
        platform: Platform name
        location_id: Location identifier
        label: Label for the screenshot

    Returns:
        Path to the saved screenshot
    """
    platform_dir = SCREENSHOTS_DIR / platform
    platform_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{location_id}_{label}_{timestamp}.png"
    filepath = platform_dir / filename

    try:
        element = await page.query_selector(selector)
        if element:
            await element.screenshot(path=str(filepath))
            logger.info(f"Element screenshot saved: {filepath.name}")
            return filepath
        else:
            logger.warning(f"Element not found for screenshot: {selector}")
            return Path("")
    except Exception as e:
        logger.warning(f"Element screenshot failed: {e}")
        return Path("")
