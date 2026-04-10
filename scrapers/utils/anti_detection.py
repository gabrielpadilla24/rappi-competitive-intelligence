"""
Anti-detection utilities for stealth scraping.
Handles User-Agent rotation, random delays, and browser fingerprint evasion.
"""

import random
import asyncio
import logging
from typing import Optional

from config.settings import (
    USER_AGENTS,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    HEADLESS,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
)

logger = logging.getLogger("scraper.anti_detection")


def get_random_user_agent() -> str:
    """Return a random User-Agent string."""
    return random.choice(USER_AGENTS)


async def random_delay(
    min_sec: float = MIN_DELAY_SECONDS,
    max_sec: float = MAX_DELAY_SECONDS,
) -> None:
    """Wait a random amount of time to simulate human behavior."""
    delay = random.uniform(min_sec, max_sec)
    logger.debug(f"Waiting {delay:.1f}s")
    await asyncio.sleep(delay)


async def human_like_delay() -> None:
    """Short delay simulating human reading/interaction time."""
    await asyncio.sleep(random.uniform(0.5, 1.5))


async def setup_stealth_browser(playwright, proxy_url: Optional[str] = None):
    """
    Create a stealth browser context with anti-detection measures.

    Returns (browser, context, page) tuple.
    """
    launch_args = {
        "headless": HEADLESS,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
        ],
    }

    if proxy_url:
        launch_args["proxy"] = {"server": proxy_url}

    browser = await playwright.chromium.launch(**launch_args)

    user_agent = get_random_user_agent()

    context = await browser.new_context(
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        user_agent=user_agent,
        locale="es-MX",
        timezone_id="America/Mexico_City",
        geolocation=None,  # Will be set per-location
        permissions=["geolocation"],
        java_script_enabled=True,
        ignore_https_errors=True,
    )

    # Apply stealth scripts to evade bot detection
    await apply_stealth_scripts(context)

    page = await context.new_page()

    # Block unnecessary resources for faster loading
    await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot}", 
                     lambda route: route.abort())

    logger.info(f"Stealth browser ready — UA: {user_agent[:60]}...")
    return browser, context, page


async def apply_stealth_scripts(context) -> None:
    """
    Inject JavaScript to mask automation indicators.
    Playwright-stealth equivalent for common detection vectors.
    """
    stealth_js = """
    // Override navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // Override navigator.plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // Override navigator.languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['es-MX', 'es', 'en-US', 'en'],
    });

    // Override chrome runtime
    window.chrome = {
        runtime: {},
    };

    // Override permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
    """

    await context.add_init_script(stealth_js)


async def simulate_human_scroll(page, scrolls: int = 3) -> None:
    """Simulate human-like scrolling behavior."""
    for _ in range(scrolls):
        scroll_amount = random.randint(200, 600)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.3, 0.8))


async def simulate_mouse_movement(page) -> None:
    """Simulate random mouse movements."""
    for _ in range(random.randint(2, 5)):
        x = random.randint(100, VIEWPORT_WIDTH - 100)
        y = random.randint(100, VIEWPORT_HEIGHT - 100)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
