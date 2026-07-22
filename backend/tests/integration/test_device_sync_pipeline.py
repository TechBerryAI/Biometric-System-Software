"""Integration: device attendance sync → logs (+ session rebuild)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.attendance.services.attendance_service import insert_attendance_logs_idempotent, run_device_sync
from app.domains.devices.services.device_service import DeviceAttendanceRecord
from tests.factories import make_employee
from tests.mocks.pyzk_simulator import SimulatedPyZKDevice


def _records_from_sim(sim: SimulatedPyZKDevice) -> list[DeviceAttendanceRecord]:
    return [
        DeviceAttendanceRecord(
            user_id=row.user_id,
            timestamp=row.timestamp,
            punch=row.punch,
            status=row.status,
        )
        for row in sim.attendance
    ]


@pytest.mark.integration
@pytest.mark.testid("BE-INT-SYNC-001")
@pytest.mark.testid("BE-INT-MDL-002")
def test_run_device_sync_inserts_logs(
    db_session: Session, simulated_device: SimulatedPyZKDevice
) -> None:
    emp = make_employee(device_user_id="TBI001", name="Unmesh Tari")
    db_session.add(emp)
    db_session.commit()

    records = _records_from_sim(simulated_device)
    device = MagicMock()
    device.fetch_attendance.return_value = records

    # wait_for / load_corrected are imported inside run_device_sync
    with (
        patch(
            "app.domains.devices.services.device_command_service.wait_for_correction_commands_clear",
            return_value=True,
        ),
        patch(
            "app.domains.attendance.services.attendance_correction_service.load_corrected_day_guards",
            return_value={},
        ),
        patch("app.ai.cache.redis_cache.AIResponseCache"),
    ):
        fetched, inserted, _placeholders = run_device_sync(db_session, device=device)

    assert fetched == len(records)
    assert inserted >= 1
    logs = db_session.execute(select(AttendanceLog)).scalars().all()
    assert len(logs) >= 1
    assert any(log.employee_code == "TBI001" for log in logs)


@pytest.mark.integration
@pytest.mark.testid("BE-INT-MDL-003")
def test_insert_attendance_logs_idempotent_from_simulator(
    db_session: Session, simulated_device: SimulatedPyZKDevice
) -> None:
    emp = make_employee(device_user_id="TBI001")
    db_session.add(emp)
    db_session.commit()

    records = _records_from_sim(simulated_device)
    inserted = insert_attendance_logs_idempotent(db_session, records, "main-entrance")
    assert inserted >= 1
    count = len(db_session.execute(select(AttendanceLog)).scalars().all())
    assert count >= 1
