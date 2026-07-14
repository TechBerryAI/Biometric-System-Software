"""Unit tests for punch classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domains.attendance.services.punch_classification import (
    classify_punch,
    device_attendance_punch_type,
    is_legacy_verify_punch_type,
    resolve_punch_types_for_day,
    summarize_day_punches,
)

UTC = ZoneInfo("UTC")


@dataclass
class _Punch:
    timestamp: datetime
    punch_type: str


@pytest.mark.testid("BE-UNIT-PUNCH-001")
def test_classify_punch_in_out_and_unknown() -> None:
    assert classify_punch(0) is True
    assert classify_punch("0") is True
    assert classify_punch("in") is True
    assert classify_punch("overtime_in") is True
    assert classify_punch("4") is True  # overtime-in

    assert classify_punch(1) is False
    assert classify_punch("1") is False
    assert classify_punch("out") is False
    assert classify_punch("overtime_out") is False
    assert classify_punch("5") is False  # overtime-out

    assert classify_punch(None) is None
    assert classify_punch("99") is None


@pytest.mark.testid("BE-UNIT-PUNCH-001")
def test_is_legacy_verify_punch_type() -> None:
    assert is_legacy_verify_punch_type("15") is True
    assert is_legacy_verify_punch_type(15) is True
    assert is_legacy_verify_punch_type("0") is False
    assert is_legacy_verify_punch_type(None) is False


@pytest.mark.testid("BE-UNIT-PUNCH-001")
def test_device_attendance_punch_type() -> None:
    assert device_attendance_punch_type(status=0, punch=1) == "0"
    assert device_attendance_punch_type(status=1, punch=0) == "1"
    # Swapped firmware: punch holds direction, status is verify mode
    assert device_attendance_punch_type(status=15, punch=0) == "0"
    assert device_attendance_punch_type(status=15, punch=1) == "1"


@pytest.mark.testid("BE-UNIT-PUNCH-001")
def test_resolve_punch_types_for_day_alternates_legacy() -> None:
    assert resolve_punch_types_for_day([]) == []
    assert resolve_punch_types_for_day(["15"]) == ["0"]
    assert resolve_punch_types_for_day(["15", "15", "15", "15"]) == ["0", "1", "0", "1"]
    # Clear mixed direction is preserved
    assert resolve_punch_types_for_day(["0", "1"]) == ["0", "1"]


@pytest.mark.testid("BE-UNIT-PUNCH-001")
def test_summarize_day_punches_with_overtime() -> None:
    t0 = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)
    punches = [
        _Punch(t0, "4"),  # overtime-in
        _Punch(t0 + timedelta(hours=10), "5"),  # overtime-out
    ]
    first_in, last_out, total_min = summarize_day_punches(punches)
    assert first_in == t0
    assert last_out == t0 + timedelta(hours=10)
    assert total_min == 600


@pytest.mark.testid("BE-UNIT-PUNCH-001")
def test_summarize_day_punches_empty() -> None:
    assert summarize_day_punches([]) == (None, None, None)
