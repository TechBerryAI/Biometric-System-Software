"""Shared punch classification helpers for attendance processing."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence
from zoneinfo import ZoneInfo


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


_VERIFY_MODE_CODES = frozenset({"2", "3", "4", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25"})


def is_legacy_verify_punch_type(punch_type: str | int | None) -> bool:
    """True when stored punch_type is a biometric verify code, not check direction."""
    if punch_type is None:
        return False
    token = str(punch_type).strip()
    return token in _VERIFY_MODE_CODES


def device_attendance_punch_type(*, status: int, punch: int) -> str:
    """
    Map a ZKTeco attlog row to a stored check-direction code.

    ``status`` encodes check-in/out (0–5). ``punch`` encodes verify mode (fingerprint, card, …)
    and must not be used as the attendance direction.
    """
    # Some firmware swaps fields: status=verify, punch=direction.
    if punch in (0, 1, 2, 3, 4, 5) and status not in (0, 1, 2, 3, 4, 5):
        return str(punch)
    if status in (0, 1, 2, 3, 4, 5):
        return str(status)
    if punch in (0, 1):
        return str(punch)
    return str(status)


class PunchLike(Protocol):
    timestamp: datetime
    punch_type: str


def resolve_punch_types_for_day(
    punch_types: Sequence[str],
    timestamps: Sequence[datetime] | None = None,
    *,
    tz_name: str | None = None,
) -> list[str]:
    """
    Repair legacy rows that stored verify mode (e.g. fingerprint=1) instead of direction.

    When every punch on a day shares the same misclassified direction, alternate IN/OUT by time
    order. A lone misclassified morning OUT (legacy fingerprint code) is treated as check-in.
    """
    if not punch_types:
        return []
    if len(punch_types) == 1:
        only = punch_types[0]
        if is_legacy_verify_punch_type(only):
            return ["0"]
        if classify_punch(only) is True:
            return ["0"]
        if classify_punch(only) is False:
            if timestamps and tz_name:
                local_hour = timestamps[0].astimezone(ZoneInfo(tz_name)).hour
                if local_hour < 12:
                    return ["0"]
            return ["1"]
        return ["0"]

    classes = [classify_punch(t) for t in punch_types]
    has_clear_direction = any(
        classify_punch(t) is True or classify_punch(t) is False
        for t in punch_types
        if not is_legacy_verify_punch_type(t)
    )
    if has_clear_direction and any(c is True for c in classes) and any(c is False for c in classes):
        return list(punch_types)

    if (
        all(is_legacy_verify_punch_type(t) or classify_punch(t) is False for t in punch_types)
        or all(is_legacy_verify_punch_type(t) or classify_punch(t) is True for t in punch_types)
        or all(is_legacy_verify_punch_type(t) or classify_punch(t) is None for t in punch_types)
    ):
        return ["0" if i % 2 == 0 else "1" for i in range(len(punch_types))]

    return list(punch_types)


def summarize_day_punches(
    punches: Sequence[PunchLike],
    *,
    tz_name: str | None = None,
) -> tuple[datetime | None, datetime | None, int | None]:
    """
    Derive first check-in, last check-out, and span minutes for one local day.

    Never copies an OUT timestamp into the IN column (or vice versa).
    """
    if not punches:
        return None, None, None

    ordered = sorted(punches, key=lambda p: p.timestamp)
    resolved_types = resolve_punch_types_for_day(
        [str(p.punch_type) for p in ordered],
        [p.timestamp for p in ordered],
        tz_name=tz_name,
    )

    ins = [
        p.timestamp
        for p, direction in zip(ordered, resolved_types, strict=True)
        if classify_punch(direction) is True
    ]
    outs = [
        p.timestamp
        for p, direction in zip(ordered, resolved_types, strict=True)
        if classify_punch(direction) is False
    ]

    first_in = min(ins) if ins else None
    last_out = max(outs) if outs else None
    total_min: int | None = None
    if first_in is not None and last_out is not None and last_out > first_in:
        total_min = int((last_out - first_in).total_seconds() // 60)
    return first_in, last_out, total_min
