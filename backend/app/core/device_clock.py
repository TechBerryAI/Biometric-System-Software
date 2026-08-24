"""Helpers for ZKTeco wall-clock writes. Never pass UTC components to set_time."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.app_timezone import UTC


def naive_local_wall_for_device(*, timezone: str, now: datetime | None = None) -> datetime:
    """Naive year/month/day/hour that ZKTeco ``set_time`` should write.

    ``now`` must be timezone-aware (any zone). It is converted into ``timezone`` first so a
    UTC instant at Monday 03:30 becomes Monday 09:00 naive for Asia/Kolkata — never 03:30.
    Naive ``now`` is rejected: Python would treat it as server-local or we would mis-tag it.
    """
    tz = ZoneInfo(timezone)
    if now is None:
        now_local = datetime.now(tz)
    else:
        if now.tzinfo is None:
            raise ValueError(
                "Refusing naive datetime for device set_time. Pass an aware instant; "
                "ZKTeco stores naive local components and UTC Monday 03:30 becomes Sunday night in IST."
            )
        now_local = now.astimezone(tz)
    wall = now_local.replace(tzinfo=None)
    if wall.tzinfo is not None:
        raise ValueError("ZKTeco set_time requires a naive local wall clock.")
    if timezone.upper() != "UTC":
        utc_wall = now_local.astimezone(UTC).replace(tzinfo=None)
        if wall == utc_wall:
            raise ValueError(
                f"Refusing to write UTC wall-clock components to timezone {timezone!r}."
            )
    return wall
