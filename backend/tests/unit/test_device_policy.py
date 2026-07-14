"""Unit tests for internal device write safety policy."""

from __future__ import annotations

import pytest

from app.core import device_policy
from app.domains.devices.services.device_command_service import _enforce_safe_write_policy


@pytest.mark.testid("BE-UNIT-POL-001")
def test_device_policy_flag_defaults() -> None:
    assert device_policy.DEVICE_WRITES_ENABLED is True
    assert device_policy.UID_REWRITE is False
    assert device_policy.ATTLOG_TIER_B_REWRITE is False


@pytest.mark.testid("BE-UNIT-POL-001")
def test_enforce_safe_write_policy_blocks_uid_rewrite() -> None:
    ok, reason = _enforce_safe_write_policy(
        payload={"user_id": "TBI001", "name": "Test", "uid": 99},
        current_on_device={"user_id": "TBI001", "name": "Test", "uid": 1},
    )
    assert ok is False
    assert reason is not None
    assert "uid rewrite" in reason


@pytest.mark.testid("BE-UNIT-POL-001")
def test_enforce_safe_write_policy_allows_unchanged_uid() -> None:
    ok, reason = _enforce_safe_write_policy(
        payload={"user_id": "TBI001", "name": "Test", "uid": 1},
        current_on_device={"user_id": "TBI001", "name": "Test", "uid": 1},
    )
    assert ok is True
    assert reason is None
