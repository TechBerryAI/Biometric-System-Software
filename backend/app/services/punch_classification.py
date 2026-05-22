"""Shared punch classification helpers for attendance processing."""

from __future__ import annotations


_IN_ALIASES = {
    "0",  # check-in
    "3",  # break-in
    "4",  # overtime-in
    "in",
    "check_in",
    "check-in",
    "i",
    "break_in",
    "break-in",
    "overtime_in",
    "overtime-in",
}

_OUT_ALIASES = {
    "1",  # check-out
    "2",  # break-out
    "5",  # overtime-out
    "out",
    "check_out",
    "check-out",
    "o",
    "break_out",
    "break-out",
    "overtime_out",
    "overtime-out",
}


def classify_punch(punch_type: str | int | None) -> bool | None:
    """Return True for in, False for out, None when unknown."""
    if punch_type is None:
        return None
    token = str(punch_type).strip().lower()
    if token in _IN_ALIASES:
        return True
    if token in _OUT_ALIASES:
        return False
    return None
