"""
Parsing utilities for scraper output normalization.
Handles price strings, time ranges, and fuzzy product matching.
"""

import re
from typing import Optional


def parse_price(text: str) -> Optional[float]:
    """
    Parse a price string into a float.

    Handles formats like: '$89', '$89.00', 'MXN 89', '$1,299.00', '89.00',
    and strings like '2 x $109' (extracts 109, not 2109).

    When a '$' sign is present, only the number immediately after the '$' is
    used. This prevents concatenation bugs like '2 x $109' → 2109.
    Returns None if the string cannot be parsed as a price.
    """
    if not text:
        return None
    # If there's an explicit $ sign, extract only the number right after it.
    # This correctly handles '2 x $109' → 109 and avoids concatenating
    # unrelated digits that appear before the '$'.
    dollar_match = re.search(r'\$\s*(\d[\d,]*(?:\.\d{1,2})?)', text)
    if dollar_match:
        cleaned = dollar_match.group(1).replace(',', '')
    else:
        # No '$': remove currency labels and spaces, then strip separators.
        cleaned = re.sub(r'[A-Za-z\s$]', '', text)
        cleaned = re.sub(r',(\d{3})', r'\1', cleaned)
        cleaned = cleaned.replace(',', '').strip()
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
    Returns (None, None) if no time found or values are outside 1–180 min.

    \d{1,3} prevents matching 4-digit numbers (years, timestamps, etc.).
    """
    if not text:
        return None, None
    # Range pattern: "25–35 min" or "25-35 min". Cap at 3 digits.
    match = re.search(r'\b(\d{1,3})\s*[–\-]\s*(\d{1,3})\s*min\b', text, re.IGNORECASE)
    if match:
        lo, hi = int(match.group(1)), int(match.group(2))
        if 1 <= lo <= hi <= 180:
            return lo, hi
    # Single value: "30 min"
    match = re.search(r'\b(\d{1,3})\s*min\b', text, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        if 1 <= val <= 180:
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
