"""
Parsing utilities for scraper output normalization.
Handles price strings, time ranges, and fuzzy product matching.
"""

import re
from typing import Optional


def parse_price(text: str) -> Optional[float]:
    """
    Parse a price string into a float.

    Handles formats like: '$89', '$89.00', 'MXN 89', '$1,299.00', '89.00'
    Returns None if the string cannot be parsed as a price.
    """
    if not text:
        return None
    # Remove currency labels, spaces
    cleaned = re.sub(r'[A-Za-z\s$]', '', text)
    # Remove thousands separators (commas before 3-digit groups)
    # e.g. "1,299.00" -> "1299.00"
    cleaned = re.sub(r',(\d{3})', r'\1', cleaned)
    # Remove any remaining commas
    cleaned = cleaned.replace(',', '')
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
        # Sanity check: prices should be positive and realistic (< 100,000 MXN)
        if value <= 0 or value > 99999:
            return None
        return value
    except (ValueError, TypeError):
        return None


def parse_time_range(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse a delivery time string into (min_minutes, max_minutes).

    Handles: '25–35 min', '25-35 min', '30 min', '30–40'
    Returns (None, None) if no time found.
    """
    if not text:
        return None, None
    # Range pattern: "25–35" or "25-35"
    match = re.search(r'(\d+)\s*[–\-]\s*(\d+)', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    # Single value: "30 min"
    match = re.search(r'(\d+)\s*min', text, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        return val, val
    return None, None


def fuzzy_match(search_terms: list[str], target: str) -> bool:
    """
    Return True if any search term is contained in the target text (case-insensitive).
    """
    target_lower = target.lower().strip()
    for term in search_terms:
        if term.lower().strip() in target_lower:
            return True
    return False
