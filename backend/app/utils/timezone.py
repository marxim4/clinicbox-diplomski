from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def clinic_today(timezone: str) -> date:
    """
    Returns the current local date for the clinic's configured timezone.

    Falls back to UTC if the stored timezone string is invalid, so a
    misconfigured clinic never causes a hard crash — it just uses UTC.
    """
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()
