"""User timezone helpers (pytz)."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def now_for_user(timezone_str: str) -> datetime:
    import pytz

    tz = pytz.timezone(timezone_str)
    return datetime.now(tz)


def utc_to_user_tz(utc_dt: datetime, tz_str: str) -> datetime:
    import pytz

    tz = pytz.timezone(tz_str)
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=dt_timezone.utc)
    return utc_dt.astimezone(tz)


def format_datetime_for_user(dt: datetime, timezone_str: str, locale: str = "en-IN") -> str:
    """Format *aware* or naive UTC datetime in the user's zone; date order hints from locale."""
    from utils.locale_format import format_date

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    local = utc_to_user_tz(dt, timezone_str)
    return format_date(local, locale)


__all__ = ["now_for_user", "utc_to_user_tz", "format_datetime_for_user"]
