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
