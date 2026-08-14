"""Unit tests for DeviceFailurePredictionService."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.ai.services.device_failure_prediction import DeviceFailurePredictionService
from app.core.config import get_settings
from app.domains.devices.models.device_command import DeviceCommandStatus
from tests.factories import make_device, make_device_command

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-UNIT-AI-DEVFAIL-001")
def test_device_failure_prediction_flags_offline_device(db_session: Session) -> None:
    device = make_device(name="offline-gate", health_status="OFFLINE")
    db_session.add(device)
    db_session.commit()

    service = DeviceFailurePredictionService(get_settings())
    result = service.predict(db_session)
    assert len(result.devices) == 1
    assert result.devices[0].device_name == "offline-gate"
    assert result.devices[0].risk_level in {"medium", "high", "critical"}


@pytest.mark.testid("BE-UNIT-AI-DEVFAIL-002")
def test_device_failure_prediction_includes_failed_commands(db_session: Session) -> None:
    device = make_device(name="failing-gate", health_status="DEGRADED")
    db_session.add(device)
    db_session.flush()
    db_session.add(
        make_device_command(
            device_id=device.name,
            status=DeviceCommandStatus.FAILED.value,
        )
    )
    db_session.commit()

    service = DeviceFailurePredictionService(get_settings())
    result = service.predict(db_session)
    assert any("recent_failed_commands" in factor for d in result.devices for factor in d.factors)
