"""Integration: post-insert punch reconciliation."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.domains.attendance.services.attendance_service import (
    count_fetched_missing_in_db,
    insert_attendance_logs_idempotent,
    run_device_sync_detailed,
)
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from tests.factories import make_device, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.integration
@pytest.mark.testid("BE-INT-RECON-001")
def test_reconciliation_zero_after_successful_insert(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIREC1")
    db_session.add(emp)
    db_session.commit()
    records = [
        DeviceAttendanceRecord(
            user_id="TBIREC1",
            timestamp=datetime(2026, 7, 21, 9, 0, tzinfo=UTC),
            punch=0,
            status=0,
        ),
        DeviceAttendanceRecord(
            user_id="TBIREC1",
            timestamp=datetime(2026, 7, 21, 18, 0, tzinfo=UTC),
            punch=0,
            status=1,
        ),
    ]
    insert_attendance_logs_idempotent(db_session, records, "main-entrance")
    assert count_fetched_missing_in_db(db_session, records, "main-entrance") == 0


@pytest.mark.integration
@pytest.mark.testid("BE-INT-RECON-002")
def test_reconciliation_detects_intentionally_omitted_row(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIREC2")
    db_session.add(emp)
    db_session.commit()
    records = [
        DeviceAttendanceRecord(
            user_id="TBIREC2",
            timestamp=datetime(2026, 7, 21, 9, 0, tzinfo=UTC),
            punch=0,
            status=0,
        ),
        DeviceAttendanceRecord(
            user_id="TBIREC2",
            timestamp=datetime(2026, 7, 21, 18, 0, tzinfo=UTC),
            punch=0,
            status=1,
        ),
    ]
    insert_attendance_logs_idempotent(db_session, records[:1], "main-entrance")
    assert count_fetched_missing_in_db(db_session, records, "main-entrance") == 1


@pytest.mark.integration
@pytest.mark.testid("BE-INT-RECON-003")
def test_run_device_sync_detailed_reports_correction_skip_reason(db_session: Session) -> None:
    device = make_device(name="main-entrance")
    db_session.add(device)
    db_session.commit()
    fake = MagicMock()
    fake.fetch_attendance.return_value = []
    with patch(
        "app.domains.devices.services.device_command_service.wait_for_correction_commands_clear",
        return_value=False,
    ):
        result = run_device_sync_detailed(db_session, device=fake, full_resync=True, device_id="main-entrance")
    assert result.skipped_reason == "correction_active"
    assert result.fetched == 0
    assert result.inserted == 0
