"""Unit tests for system governance / freeze controls."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.domains.ops.services.system_governance_service import assert_device_write_allowed, ensure_control_state
from tests.factories import make_control_state, make_device


@pytest.mark.testid("BE-UNIT-GOV-001")
def test_ensure_control_state_creates_singleton(db_session: Session) -> None:
    state = ensure_control_state(db_session)
    assert state.singleton_key == "global"
    assert state.maintenance_mode is False
    assert state.emergency_freeze_mode is False

    again = ensure_control_state(db_session)
    assert again is state


@pytest.mark.testid("BE-UNIT-GOV-001")
def test_assert_device_write_allowed_when_normal(db_session: Session) -> None:
    db_session.add(make_control_state())
    db_session.add(make_device(name="main-entrance", mode="NORMAL"))
    db_session.commit()

    allowed, reason = assert_device_write_allowed(db_session, device_id="main-entrance")
    assert allowed is True
    assert reason is None


@pytest.mark.testid("BE-UNIT-GOV-001")
def test_assert_device_write_blocked_by_emergency_freeze(db_session: Session) -> None:
    db_session.add(make_control_state(emergency_freeze_mode=True))
    db_session.add(make_device(name="main-entrance"))
    db_session.commit()

    allowed, reason = assert_device_write_allowed(db_session, device_id="main-entrance")
    assert allowed is False
    assert reason is not None
    assert "freeze" in reason.lower()
