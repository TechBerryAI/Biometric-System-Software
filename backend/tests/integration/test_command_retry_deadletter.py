"""Integration: command execution hash, claim priority, retry → dead-letter."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.devices.models.device_command import DeviceCommandStatus
from app.domains.devices.services.device_command_service import (
    _execution_hash,
    _mark_retry_or_terminal,
    claim_pending_commands,
    process_command,
)
from tests.factories import make_control_state, make_device, make_device_command


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CMD-001")
@pytest.mark.testid("BE-INT-MDL-006")
def test_execution_hash_stable_per_attempt(db_session: Session) -> None:
    cmd = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "Hash"},
        idempotency_key="hash-cmd-1",
    )
    db_session.add(cmd)
    db_session.commit()

    h1 = _execution_hash(cmd, 1)
    h2 = _execution_hash(cmd, 1)
    h3 = _execution_hash(cmd, 2)
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CMD-001")
def test_claim_priority_correct_over_upsert(db_session: Session) -> None:
    now = datetime.now(ZoneInfo("UTC"))
    upsert = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "A"},
        status=DeviceCommandStatus.PENDING.value,
        idempotency_key="prio-upsert",
    )
    upsert.created_at = now - timedelta(hours=1)
    correct = make_device_command(
        command_type="CORRECT_ATTENDANCE",
        payload={"employee_id": 1, "local_date": "2026-07-14", "user_id": "TBI001"},
        status=DeviceCommandStatus.PENDING.value,
        idempotency_key="prio-correct",
    )
    correct.created_at = now
    db_session.add_all([upsert, correct])
    db_session.commit()

    claimed = claim_pending_commands(db_session)
    assert claimed[0].command_type == "CORRECT_ATTENDANCE"


@pytest.mark.integration
@pytest.mark.testid("BE-INT-CMD-002")
def test_process_command_failure_transitions_to_retry_then_dead_letter(
    db_session: Session,
) -> None:
    db_session.add(make_control_state())
    settings = get_settings()
    db_session.add(make_device(name="main-entrance", ip_address="192.168.1.85"))
    cmd = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBIFAIL", "name": "Fail Me"},
        status=DeviceCommandStatus.PENDING.value,
        idempotency_key="fail-cmd-1",
    )
    db_session.add(cmd)
    db_session.commit()
    db_session.refresh(cmd)

    # Drive retry/dead-letter via _mark_retry_or_terminal directly for determinism,
    # then also exercise process_command exception path once.
    for _ in range(settings.command_max_retries - 1):
        _mark_retry_or_terminal(cmd, settings=settings, error_message="boom")
        assert cmd.status == DeviceCommandStatus.RETRYING.value

    _mark_retry_or_terminal(cmd, settings=settings, error_message="final boom")
    assert cmd.status == DeviceCommandStatus.DEAD_LETTER.value
    assert cmd.completed_at is not None

    # process_command path: exception during device work → retry/deadletter helper
    cmd2 = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBIFAIL2", "name": "Fail2"},
        status=DeviceCommandStatus.PENDING.value,
        idempotency_key="fail-cmd-2",
    )
    db_session.add(cmd2)
    db_session.commit()

    fake_lock = MagicMock()
    with (
        patch(
            "app.domains.devices.services.device_command_service._acquire_lock",
            return_value=(None, fake_lock, "lock-key"),
        ),
        patch(
            "app.domains.devices.services.device_command_service.DeviceService",
        ) as device_cls,
        patch("app.domains.devices.services.device_command_service._LockHeartbeat") as hb_cls,
    ):
        hb_cls.return_value = MagicMock()
        device_cls.return_value.detect_firmware_fingerprint.return_value = {"firmware_version": "sim"}
        device_cls.return_value.fetch_users.side_effect = RuntimeError("device exploded")
        process_command(db_session, cmd2, settings=settings, worker_id="test-worker")
        db_session.commit()
        db_session.refresh(cmd2)

    assert cmd2.status in {
        DeviceCommandStatus.RETRYING.value,
        DeviceCommandStatus.DEAD_LETTER.value,
        DeviceCommandStatus.FAILED.value,
    }
    assert cmd2.last_error is not None
