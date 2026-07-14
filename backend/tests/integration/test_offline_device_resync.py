"""Integration: offline device recovers and sync succeeds after failure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.attendance_service import run_device_sync
from app.shared.device_exceptions import DeviceFetchError
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from tests.factories import make_employee
from tests.mocks.pyzk_simulator import SimulatedPyZKDevice


@pytest.mark.integration
@pytest.mark.testid("BE-INT-OFFLINE-001")
def test_offline_then_resync_succeeds(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBI099")
    db_session.add(emp)
    db_session.commit()

    sim = SimulatedPyZKDevice(fail_rate=1.0)
    assert sim.fail_rate == 1.0

    device = MagicMock()
    device.fetch_attendance.side_effect = DeviceFetchError("simulated offline")

    with (
        patch(
            "app.domains.devices.services.device_command_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service.load_corrected_employee_days",
            return_value=set(),
        ),
        patch("app.ai.cache.redis_cache.AIResponseCache"),
    ):
        with pytest.raises(DeviceFetchError):
            run_device_sync(db_session, device=device)

    # Device comes back online
    from datetime import datetime
    from zoneinfo import ZoneInfo

    sim.fail_rate = 0.0
    ts = datetime.now(ZoneInfo("UTC"))
    device.fetch_attendance.side_effect = None
    device.fetch_attendance.return_value = [
        DeviceAttendanceRecord(user_id="TBI099", timestamp=ts, punch=0, status=0),
    ]

    with (
        patch(
            "app.domains.devices.services.device_command_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service.load_corrected_employee_days",
            return_value=set(),
        ),
        patch("app.ai.cache.redis_cache.AIResponseCache"),
    ):
        fetched, inserted, _ = run_device_sync(db_session, device=device)

    assert fetched == 1
    assert inserted >= 1
    logs = db_session.execute(select(AttendanceLog)).scalars().all()
    assert len(logs) >= 1
