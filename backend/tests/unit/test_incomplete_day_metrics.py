"""Unit tests for incomplete attendance-day metrics."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.attendance.services.incomplete_day_metrics import count_incomplete_attendance_days
from tests.factories import make_attendance_log, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-UNIT-OPEN-DAY-001")
def test_count_incomplete_days_single_punch(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "timezone", "UTC")
    monkeypatch.setattr(settings, "open_day_min_span_minutes", 5)
    # Use a fixed weekday in the past relative to "now" — patch datetime via lookback window.
    emp = make_employee(device_user_id="TBIOPEN1")
    db_session.add(emp)
    # Yesterday-ish: use a known recent weekday punch only once
    day = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)  # Tuesday
    db_session.add(make_attendance_log(employee=emp, punched_at=day, punch_type="0"))
    db_session.commit()

    # Force "today" context by using include_today and a wide lookback that includes 21 Jul
    # when tests run on 2026-07-22+.
    count = count_incomplete_attendance_days(
        db_session, lookback_days=60, settings=settings, include_today=True
    )
    assert count >= 1
