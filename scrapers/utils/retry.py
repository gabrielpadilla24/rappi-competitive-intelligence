"""
Retry logic with exponential backoff for resilient scraping.
"""

import asyncio
import logging
import functools
from typing import Callable, Any, Optional, Type

from config.settings import MAX_RETRIES, RETRY_BACKOFF_BASE

logger = logging.getLogger("scraper.retry")


class ScrapingError(Exception):
    """Base exception for scraping failures."""
    pass


class BlockedError(ScrapingError):
    """Raised when the platform blocks/rate-limits the scraper."""
    pass


class ElementNotFoundError(ScrapingError):
    """Raised when an expected DOM element is not found."""
    pass


class LocationError(ScrapingError):
    """Raised when location setting fails."""
    pass


async def retry_async(
    func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    backoff_base: float = RETRY_BACKOFF_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
    **kwargs,
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        backoff_base: Base delay in seconds (doubles each retry)
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called on each retry (receives attempt, exception)

    Returns:
        The function's return value on success

    Raises:
        The last exception if all retries fail
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(
                    f"All {max_retries} retries exhausted for {func.__name__}: {e}"
                )
                raise

            delay = backoff_base * (2 ** attempt)
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed for "
                f"{func.__name__}: {e}. Retrying in {delay}s..."
            )

            if on_retry:
                on_retry(attempt, e)

            await asyncio.sleep(delay)

    raise last_exception


def with_retry(
    max_retries: int = MAX_RETRIES,
    backoff_base: float = RETRY_BACKOFF_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator version of retry_async.

    Usage:
        @with_retry(max_retries=3)
        async def my_function():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                *args,
                max_retries=max_retries,
                backoff_base=backoff_base,
                retryable_exceptions=retryable_exceptions,
                **kwargs,
            )
        return wrapper
    return decorator
