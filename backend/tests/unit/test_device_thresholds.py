"""Unit tests for biometric threshold management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domains.devices.services.device_config_service import (
    THRESHOLD_DEFAULTS,
    get_thresholds,
    update_thresholds,
    validate_thresholds,
)


@pytest.mark.testid("BE-UNIT-THRESH-001")
def test_validate_thresholds_ok() -> None:
    cleaned = validate_thresholds({"fingerprint_match_score": 55, "face_match_score": 80})
    assert cleaned["fingerprint_match_score"] == 55


@pytest.mark.testid("BE-UNIT-THRESH-002")
def test_validate_thresholds_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        validate_thresholds({"nope": 1})


@pytest.mark.testid("BE-UNIT-THRESH-003")
def test_validate_thresholds_rejects_oob() -> None:
    with pytest.raises(ValueError, match="between"):
        validate_thresholds({"fingerprint_match_score": 200})


@pytest.mark.testid("BE-UNIT-THRESH-004")
def test_get_thresholds_defaults() -> None:
    device = MagicMock(capabilities=None, timezone="UTC", connectivity_mode="pull", branch_id=None, config_version=1)
    assert get_thresholds(device) == THRESHOLD_DEFAULTS


@pytest.mark.testid("BE-UNIT-THRESH-005")
def test_update_thresholds_persists(db_session) -> None:
    from tests.factories import make_device

    device = make_device(name="thresh-device")
    device.capabilities = {}
    device.config_version = 0
    db_session.add(device)
    db_session.commit()

    with patch(
        "app.domains.devices.services.device_config_service.enqueue_device_command",
        return_value=MagicMock(),
    ):
        update_thresholds(db_session, device, {"face_match_score": 88}, apply_to_device=True)
    db_session.commit()
    assert get_thresholds(device)["face_match_score"] == 88
    assert device.config_version == 1
