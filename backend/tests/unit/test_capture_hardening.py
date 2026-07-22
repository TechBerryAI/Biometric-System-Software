"""Unit: default device prefers push+pull and attlog clear is refused."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core import device_policy
from app.domains.devices.services.device_attlog_protocol import refuse_device_attlog_clear
from app.domains.devices.services.device_registry_service import create_device, ensure_default_device
from app.shared.device_exceptions import AttlogCorrectionNotSupported
from tests.factories import make_device


@pytest.mark.testid("BE-UNIT-CAPTURE-001")
def test_ensure_default_device_upgrades_pull_to_both(db_session: Session) -> None:
    settings = get_settings()
    device = make_device(name=settings.zk_device_id, connectivity_mode="pull")
    db_session.add(device)
    db_session.commit()

    ensured = ensure_default_device(db_session, settings=settings)
    assert ensured.connectivity_mode == "both"


@pytest.mark.testid("BE-UNIT-CAPTURE-002")
def test_create_device_defaults_to_both(db_session: Session) -> None:
    row = create_device(db_session, name="lobby-both", ip_address="10.0.0.50")
    db_session.commit()
    assert row.connectivity_mode == "both"


@pytest.mark.testid("BE-UNIT-CAPTURE-003")
def test_refuse_device_attlog_clear_by_default() -> None:
    assert device_policy.ALLOW_DEVICE_ATTLOG_CLEAR is False
    with pytest.raises(AttlogCorrectionNotSupported, match="refused"):
        refuse_device_attlog_clear(reason="unit-test")
