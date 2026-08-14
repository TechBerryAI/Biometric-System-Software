"""Process-level timezone override sourced from the devices table / Settings UI."""

from __future__ import annotations

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
