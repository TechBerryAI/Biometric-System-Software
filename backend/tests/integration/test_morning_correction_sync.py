"""Integration: morning IN-only correction must not block midday/evening sync inserts."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.attendance_service import run_device_sync_detailed
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from tests.factories import make_device, make_employee

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CORR-SYNC-001")
def test_morning_correction_sync_imports_midday_and_evening(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIMEZONE", "Asia/Kolkata")
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "timezone", "Asia/Kolkata")

    device = make_device(name="main-entrance")
    emp = make_employee(device_user_id="TBICORR1")
    db_session.add_all([device, emp])
    db_session.flush()

    morning_in = datetime(2026, 7, 21, 9, 33, 19, tzinfo=IST)
    deleted_near = datetime(2026, 7, 21, 9, 49, 19, tzinfo=IST)
    midday = datetime(2026, 7, 21, 12, 0, 0, tzinfo=IST)
    evening = datetime(2026, 7, 21, 18, 30, 0, tzinfo=IST)
    # Late admin action time — must not extend the sync wall.
    completed = datetime(2026, 7, 21, 14, 3, 41, tzinfo=IST)

    db_session.add(
        DeviceCommand(
            device_id="main-entrance",
            command_type="CORRECT_ATTENDANCE",
            status=DeviceCommandStatus.SUCCESS.value,
            payload={
                "user_id": "TBICORR1",
                "local_date": "2026-07-21",
                "new_check_in": morning_in.isoformat(),
                "new_check_out": None,
                "delete_timestamps": [deleted_near.isoformat()],
            },
            idempotency_key=f"test-corr-sync-{uuid4()}",
            completed_at=completed,
            created_at=completed,
        )
    )
    # Corrected morning IN already in DB (as replace_employee_day_logs would leave it),
    # stored in UTC like every other punch (SQLite keeps the UTC wall clock, naive).
    db_session.add(
        AttendanceLog(
            employee_code="TBICORR1",
            timestamp=morning_in.astimezone(UTC),
            device_id="main-entrance",
            punch_type="0",
        )
    )
    db_session.commit()

    device_rows = [
        DeviceAttendanceRecord(user_id="TBICORR1", timestamp=morning_in, punch=0, status=0),
        DeviceAttendanceRecord(user_id="TBICORR1", timestamp=deleted_near, punch=1, status=1),
        DeviceAttendanceRecord(user_id="TBICORR1", timestamp=midday, punch=0, status=0),
        DeviceAttendanceRecord(user_id="TBICORR1", timestamp=evening, punch=1, status=1),
    ]
    fake = MagicMock()
    fake.fetch_attendance.return_value = device_rows

    with patch(
        "app.domains.devices.services.device_command_service.wait_for_correction_commands_clear",
        return_value=True,
    ):
        result = run_device_sync_detailed(
            db_session, device=fake, full_resync=True, device_id="main-entrance"
        )

    assert result.fetched == 4
    assert result.inserted == 2  # midday + evening only
    assert result.skipped_corrected_punches == 2  # morning IN replay + deleted near-dup
    assert result.punches_missing_after_insert == 0

    # Punches are persisted as UTC; SQLite hands them back naive.
    stamps = {
        (row.timestamp.replace(tzinfo=UTC) if row.timestamp.tzinfo is None else row.timestamp).astimezone(IST)
        for row in db_session.execute(
            select(AttendanceLog).where(AttendanceLog.employee_code == "TBICORR1")
        ).scalars().all()
    }
    stamps = {ts.replace(microsecond=0) for ts in stamps}
    assert morning_in.replace(microsecond=0) in stamps
    assert midday.replace(microsecond=0) in stamps
    assert evening.replace(microsecond=0) in stamps
    assert deleted_near.replace(microsecond=0) not in stamps
    count = db_session.execute(
        select(func.count()).select_from(AttendanceLog).where(AttendanceLog.employee_code == "TBICORR1")
    ).scalar_one()
    assert count == 3
