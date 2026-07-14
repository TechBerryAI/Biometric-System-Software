"""Integration: correction SUCCESS path via finalize_pending_correction_for_command."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.devices.models.device_command import DeviceCommandStatus
from app.domains.attendance.services.attendance_correction_service import (
    CORRECTION_STATUS_APPLIED,
    finalize_pending_correction_for_command,
)
from tests.factories import make_attendance_log, make_device_command, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CORR-001")
def test_finalize_pending_correction_success_path(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBICOR1", name="Correct Me")
    db_session.add(emp)
    db_session.flush()

    day = date(2026, 7, 14)
    old_in = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)
    old_out = datetime(2026, 7, 14, 17, 0, tzinfo=UTC)
    new_in = datetime(2026, 7, 14, 9, 15, tzinfo=UTC)
    new_out = datetime(2026, 7, 14, 17, 30, tzinfo=UTC)

    db_session.add(make_attendance_log(employee=emp, punched_at=old_in, punch_type="0"))
    db_session.add(make_attendance_log(employee=emp, punched_at=old_out, punch_type="1"))
    db_session.flush()

    cmd = make_device_command(
        command_type="CORRECT_ATTENDANCE",
        payload={
            "employee_id": emp.id,
            "local_date": day.isoformat(),
            "user_id": emp.device_user_id,
            "new_check_in": new_in.isoformat(),
            "new_check_out": new_out.isoformat(),
            "db_only": False,
        },
        status=DeviceCommandStatus.SUCCESS.value,
        idempotency_key="corr-finalize-001",
    )
    db_session.add(cmd)
    db_session.commit()

    result = finalize_pending_correction_for_command(db_session, cmd.command_uuid)
    assert result is not None
    assert result.status == CORRECTION_STATUS_APPLIED
    assert result.device_updated is True
    assert result.new_check_in == new_in

    logs = db_session.execute(
        select(AttendanceLog).where(AttendanceLog.employee_code == emp.device_user_id)
    ).scalars().all()
    timestamps = {log.timestamp.replace(tzinfo=UTC) if log.timestamp.tzinfo is None else log.timestamp for log in logs}
    # SQLite may drop tzinfo; compare via isoformat without relying on tz
    assert any(abs((t.replace(tzinfo=UTC) - new_in).total_seconds()) < 2 for t in timestamps)
    assert any(abs((t.replace(tzinfo=UTC) - new_out).total_seconds()) < 2 for t in timestamps)
    assert all(abs((t.replace(tzinfo=UTC) - old_in).total_seconds()) > 1 for t in timestamps)
