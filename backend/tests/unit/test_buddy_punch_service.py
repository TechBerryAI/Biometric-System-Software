"""Unit tests for BuddyPunchService."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.ai.services.buddy_punch_service import BuddyPunchService
from app.core.config import get_settings
from tests.factories import make_attendance_log, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-UNIT-AI-BUDDY-001")
def test_buddy_punch_detects_rapid_sequential_punches(db_session: Session) -> None:
    settings = get_settings()
    service = BuddyPunchService(settings, window_seconds=60)
    tz = ZoneInfo(settings.timezone)
    base = datetime.now(tz).astimezone(UTC) - timedelta(minutes=5)

    emp_a = make_employee(device_user_id="BUDDYA")
    emp_b = make_employee(device_user_id="BUDDYB")
    db_session.add_all([emp_a, emp_b])
    db_session.flush()

    db_session.add(make_attendance_log(employee=emp_a, punched_at=base, punch_type="0"))
    db_session.add(make_attendance_log(employee=emp_b, punched_at=base + timedelta(seconds=20), punch_type="0"))
    db_session.commit()

    result = service.detect(db_session, lookback_days=1)
    assert len(result.alerts) == 1
    assert set(result.alerts[0].employee_codes) == {"BUDDYA", "BUDDYB"}


@pytest.mark.testid("BE-UNIT-AI-BUDDY-002")
def test_buddy_punch_ignores_same_employee(db_session: Session) -> None:
    settings = get_settings()
    service = BuddyPunchService(settings)
    now = datetime.now(UTC)
    emp = make_employee(device_user_id="SOLO001")
    db_session.add(emp)
    db_session.flush()
    db_session.add(make_attendance_log(employee=emp, punched_at=now, punch_type="0"))
    db_session.add(make_attendance_log(employee=emp, punched_at=now + timedelta(seconds=10), punch_type="1"))
    db_session.commit()

    result = service.detect(db_session, lookback_days=1)
    assert result.alerts == []
