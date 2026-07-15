"""Integration: duplicate punch prevention at insert time."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.attendance_service import insert_attendance_logs_idempotent
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from tests.factories import make_employee


@pytest.mark.integration
@pytest.mark.testid("BE-INT-DUP-001")
def test_duplicate_punch_insert_keeps_single_row(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIDUP1")
    db_session.add(emp)
    db_session.commit()

    ts = datetime(2026, 7, 14, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
    record = DeviceAttendanceRecord(user_id="TBIDUP1", timestamp=ts, punch=0, status=0)

    first = insert_attendance_logs_idempotent(db_session, [record], "main-entrance")
    second = insert_attendance_logs_idempotent(db_session, [record], "main-entrance")

    assert first == 1
    assert second == 0
    count = db_session.execute(select(func.count()).select_from(AttendanceLog)).scalar_one()
    assert count == 1


@pytest.mark.integration
@pytest.mark.testid("BE-INT-DUP-002")
def test_near_duplicate_within_window_is_skipped(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same employee + punch direction within the duplicate window must not create a second row."""
    from app.core.config import get_settings

    monkeypatch.setenv("DUPLICATE_PUNCH_WINDOW_SECONDS", "30")
    get_settings.cache_clear()

    emp = make_employee(device_user_id="TBIDUP2")
    db_session.add(emp)
    db_session.commit()

    tz = ZoneInfo("UTC")
    first_ts = datetime(2026, 7, 14, 9, 0, 0, tzinfo=tz)
    near_ts = datetime(2026, 7, 14, 9, 0, 12, tzinfo=tz)
    first = insert_attendance_logs_idempotent(
        db_session,
        [DeviceAttendanceRecord(user_id="TBIDUP2", timestamp=first_ts, punch=0, status=0)],
        "main-entrance",
    )
    near = insert_attendance_logs_idempotent(
        db_session,
        [DeviceAttendanceRecord(user_id="TBIDUP2", timestamp=near_ts, punch=0, status=0)],
        "main-entrance",
    )
    assert first == 1
    assert near == 0
    count = db_session.execute(select(func.count()).select_from(AttendanceLog)).scalar_one()
    assert count == 1
    get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.testid("BE-INT-DUP-003")
def test_in_then_out_within_window_both_kept(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real In→Out within 30s must both store — only same-direction near-dups are collapsed."""
    from app.core.config import get_settings

    monkeypatch.setenv("DUPLICATE_PUNCH_WINDOW_SECONDS", "30")
    get_settings.cache_clear()

    emp = make_employee(device_user_id="TBIDUP3")
    db_session.add(emp)
    db_session.commit()

    tz = ZoneInfo("UTC")
    cin = insert_attendance_logs_idempotent(
        db_session,
        [DeviceAttendanceRecord(user_id="TBIDUP3", timestamp=datetime(2026, 7, 14, 9, 0, 0, tzinfo=tz), punch=0, status=0)],
        "main-entrance",
    )
    cout = insert_attendance_logs_idempotent(
        db_session,
        [DeviceAttendanceRecord(user_id="TBIDUP3", timestamp=datetime(2026, 7, 14, 9, 0, 10, tzinfo=tz), punch=0, status=1)],
        "main-entrance",
    )
    assert cin == 1
    assert cout == 1
    count = db_session.execute(select(func.count()).select_from(AttendanceLog)).scalar_one()
    assert count == 2
    get_settings.cache_clear()
