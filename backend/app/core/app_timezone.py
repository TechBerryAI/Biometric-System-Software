"""Process-level timezone override sourced from the devices table / Settings UI."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"
UTC = ZoneInfo("UTC")

_timezone_override: str | None = None


def get_timezone_override() -> str | None:
    return _timezone_override


def set_app_timezone(timezone: str | None) -> None:
    """Prefer the registered device timezone over bootstrap TIMEZONE env/defaults."""
    global _timezone_override
    value = (timezone or "").strip()
    _timezone_override = value or None


def clear_app_timezone() -> None:
    global _timezone_override
    _timezone_override = None


def coerce_device_timezone(timezone: str | None) -> str:
    """UTC (or blank) is treated as unset — this site's terminals keep IST wall clocks."""
    value = (timezone or "").strip()
    if not value or value.upper() == "UTC":
        return DEFAULT_TIMEZONE
    return value


def as_aware(dt: datetime, tz: ZoneInfo) -> datetime:
    """Interpret naive datetimes as ``tz`` wall clock; convert aware values into ``tz``.

    Never call ``naive.astimezone()`` — Python treats naive as the *server* zone.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def to_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    """Normalize a punch timestamp to UTC for storage."""
    return as_aware(dt, tz).astimezone(UTC)


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return as_aware(dt, tz).date()


def local_today(tz: ZoneInfo | str) -> date:
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    return datetime.now(zone).date()
