"""Unit tests for attendance helper utilities."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domains.attendance.services.attendance_helpers import day_bounds_utc, local_date, pair_logs_for_day
from tests.factories import make_attendance_log, make_employee

UTC = ZoneInfo("UTC")
IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.testid("BE-UNIT-HELP-001")
def test_day_bounds_utc_for_ist() -> None:
    start, end = day_bounds_utc(date(2026, 7, 14), "Asia/Kolkata")
    assert start.tzinfo is not None
    assert end - start == timedelta(days=1)
    # IST midnight = previous day 18:30 UTC
    assert start == datetime(2026, 7, 13, 18, 30, tzinfo=UTC)


@pytest.mark.testid("BE-UNIT-HELP-001")
def test_local_date() -> None:
    dt = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)
    assert local_date(dt, IST) == date(2026, 7, 14)


@pytest.mark.testid("BE-UNIT-HELP-001")
def test_pair_logs_for_day_complete_and_missing() -> None:
    emp = make_employee(device_user_id="TBI001")
    t0 = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)
    cin = make_attendance_log(employee=emp, punched_at=t0, punch_type="0")
    cout = make_attendance_log(employee=emp, punched_at=t0 + timedelta(hours=8), punch_type="1")
    orphan_in = make_attendance_log(employee=emp, punched_at=t0 + timedelta(hours=10), punch_type="0")

    pairs = pair_logs_for_day([cin, cout, orphan_in], UTC, duplicate_window_seconds=30)
    assert len(pairs) == 2
    assert pairs[0][2] == "complete"
    assert pairs[0][0] is cin and pairs[0][1] is cout
    assert pairs[1][2] == "missing_check_out"
    assert pairs[1][0] is orphan_in and pairs[1][1] is None


@pytest.mark.testid("BE-UNIT-HELP-002")
def test_pair_logs_for_day_leading_out_kept_as_first_in() -> None:
    """Device-coded leading OUT must still start the first session."""
    emp = make_employee(device_user_id="TBI002")
    t0 = datetime(2026, 7, 14, 6, 10, tzinfo=UTC)
    early = make_attendance_log(employee=emp, punched_at=t0, punch_type="1")
    mid = make_attendance_log(employee=emp, punched_at=t0 + timedelta(hours=3), punch_type="0")
    late = make_attendance_log(employee=emp, punched_at=t0 + timedelta(hours=12), punch_type="1")

    pairs = pair_logs_for_day([early, mid, late], UTC, duplicate_window_seconds=30)
    assert len(pairs) == 2
    assert pairs[0][0] is early and pairs[0][1] is mid and pairs[0][2] == "complete"
    assert pairs[1][0] is late and pairs[1][1] is None and pairs[1][2] == "missing_check_out"
