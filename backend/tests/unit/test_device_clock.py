"""Unit: IST wall clock for ZKTeco set_time must never write UTC components."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.device_clock import naive_local_wall_for_device

UTC = ZoneInfo("UTC")
IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.testid("BE-UNIT-CLOCK-001")
def test_ist_wall_from_utc_instant_is_local_not_utc() -> None:
    now = datetime(2026, 8, 24, 3, 30, tzinfo=UTC)  # Monday 09:00 IST
    wall = naive_local_wall_for_device(timezone="Asia/Kolkata", now=now)
    assert wall == datetime(2026, 8, 24, 9, 0)
    assert wall.tzinfo is None


@pytest.mark.testid("BE-UNIT-CLOCK-003")
def test_ist_wall_from_ist_instant_keeps_local_components() -> None:
    now = datetime(2026, 8, 24, 9, 0, tzinfo=IST)
    wall = naive_local_wall_for_device(timezone="Asia/Kolkata", now=now)
    assert wall == datetime(2026, 8, 24, 9, 0)
    assert wall.tzinfo is None


@pytest.mark.testid("BE-UNIT-CLOCK-002")
def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        naive_local_wall_for_device(timezone="Asia/Kolkata", now=datetime(2026, 8, 24, 3, 30))
