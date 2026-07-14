"""Unit tests for device command execution-hash replay stability."""

from __future__ import annotations

import pytest

from app.domains.devices.services.device_command_service import _execution_hash
from tests.factories import make_device_command


@pytest.mark.testid("BE-UNIT-POL-001")
def test_execution_hash_stable_for_same_attempt() -> None:
    command = make_device_command(
        device_id="main-entrance",
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "Unmesh Tari"},
    )
    first = _execution_hash(command, 1)
    second = _execution_hash(command, 1)
    assert first == second
    assert len(first) == 64


@pytest.mark.testid("BE-UNIT-POL-001")
def test_execution_hash_changes_when_attempt_changes() -> None:
    command = make_device_command(
        device_id="main-entrance",
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "Unmesh Tari"},
    )
    attempt_1 = _execution_hash(command, 1)
    attempt_2 = _execution_hash(command, 2)
    assert attempt_1 != attempt_2
