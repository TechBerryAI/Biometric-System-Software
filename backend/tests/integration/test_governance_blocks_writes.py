"""Integration: governance freeze / READ_ONLY blocks device writes."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.domains.ops.services.system_governance_service import assert_device_write_allowed
from tests.factories import make_control_state, make_device


@pytest.mark.integration
@pytest.mark.testid("BE-INT-GOV-001")
@pytest.mark.testid("BE-INT-MDL-005")
def test_governance_blocks_writes_on_emergency_freeze(db_session: Session) -> None:
    db_session.add(make_control_state(emergency_freeze_mode=True))
    db_session.add(make_device(name="main-entrance", mode="NORMAL"))
    db_session.commit()

    allowed, reason = assert_device_write_allowed(db_session, device_id="main-entrance")
    assert allowed is False
    assert reason is not None
    assert "freeze" in reason.lower()


@pytest.mark.integration
@pytest.mark.testid("BE-INT-GOV-001")
def test_governance_blocks_writes_when_device_read_only(db_session: Session) -> None:
    db_session.add(make_control_state())
    db_session.add(make_device(name="main-entrance", mode="READ_ONLY"))
    db_session.commit()

    allowed, reason = assert_device_write_allowed(db_session, device_id="main-entrance")
    assert allowed is False
    assert reason is not None
    assert "READ_ONLY" in reason
