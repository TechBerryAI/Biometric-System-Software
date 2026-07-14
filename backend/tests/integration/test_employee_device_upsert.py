"""Integration: employee create → UPSERT_USER enqueue / claim priority."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.domains.devices.models.device_command import DeviceCommandStatus
from app.domains.devices.services.device_command_service import claim_pending_commands, enqueue_device_command
from tests.factories import make_control_state, make_device_command, make_employee, make_mapping


@pytest.mark.integration
@pytest.mark.testid("BE-INT-UPSERT-001")
@pytest.mark.testid("BE-INT-MDL-001")
def test_enqueue_upsert_user_and_process(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBIUPS1", name="Upsert Person")
    db_session.add(emp)
    db_session.flush()
    db_session.add(make_mapping(employee=emp))
    db_session.add(make_control_state())
    db_session.commit()

    command = enqueue_device_command(
        db_session,
        device_id="main-entrance",
        command_type="UPSERT_USER",
        payload={"user_id": emp.device_user_id, "name": emp.name, "uid": emp.device_uid or 1},
        correlation_id="corr-upsert-1",
        created_by=None,
        initiated_from="test:upsert",
    )
    db_session.commit()
    assert command.status == DeviceCommandStatus.PENDING.value
    assert command.command_type == "UPSERT_USER"

    with patch("app.domains.devices.services.device_command_service.process_command") as process:
        def _succeed(db, cmd, **_kwargs):
            cmd.status = DeviceCommandStatus.SUCCESS.value
            cmd.completed_at = datetime.now(ZoneInfo("UTC"))

        process.side_effect = _succeed
        process(db_session, command)
        db_session.commit()
        db_session.refresh(command)

    assert command.status == DeviceCommandStatus.SUCCESS.value
    process.assert_called_once()


@pytest.mark.integration
@pytest.mark.testid("BE-INT-MDL-001")
def test_claim_pending_prioritizes_correct_attendance(db_session: Session) -> None:
    now = datetime.now(ZoneInfo("UTC"))
    upsert = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "A"},
        status=DeviceCommandStatus.PENDING.value,
        idempotency_key="claim-upsert-1",
    )
    upsert.created_at = now - timedelta(seconds=10)
    correct = make_device_command(
        command_type="CORRECT_ATTENDANCE",
        payload={"employee_id": 1, "local_date": "2026-07-14", "user_id": "TBI001"},
        status=DeviceCommandStatus.PENDING.value,
        idempotency_key="claim-correct-1",
    )
    correct.created_at = now
    db_session.add_all([upsert, correct])
    db_session.commit()

    claimed = claim_pending_commands(db_session)
    db_session.commit()

    assert len(claimed) == 1
    assert claimed[0].command_type == "CORRECT_ATTENDANCE"
    assert claimed[0].status == DeviceCommandStatus.RUNNING.value
