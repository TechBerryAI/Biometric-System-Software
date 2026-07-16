"""Unit tests for drift persistence."""

from __future__ import annotations

import pytest

from app.domains.devices.models.device_user_drift import DeviceUserDrift
from app.domains.devices.services.drift_service import (
    DRIFT_MISSING_MAPPING,
    DRIFT_MISSING_ON_DEVICE,
    mark_drift_resolved,
    persist_drift_events,
)
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.employees.models.employee import Employee


@pytest.mark.testid("BE-UNIT-DRIFT-001")
def test_persist_drift_creates_and_resolves(db_session) -> None:
    emp = Employee(device_user_id="100", name="Bob")
    db_session.add(emp)
    db_session.flush()
    db_session.add(
        DeviceUserMapping(
            employee_uuid=emp.employee_uuid,
            device_id="gate-1",
            device_user_id="100",
            active=True,
        )
    )
    db_session.commit()

    first = persist_drift_events(
        db_session,
        device_id="gate-1",
        missing_on_device=["100"],
        missing_mapping=["200"],
    )
    db_session.commit()
    assert first["created"] == 2
    assert first["open"] == 2

    open_rows = db_session.query(DeviceUserDrift).filter_by(status="open").all()
    assert len(open_rows) == 2
    types = {r.drift_type for r in open_rows}
    assert types == {DRIFT_MISSING_ON_DEVICE, DRIFT_MISSING_MAPPING}

    second = persist_drift_events(
        db_session,
        device_id="gate-1",
        missing_on_device=[],
        missing_mapping=[],
    )
    db_session.commit()
    assert second["resolved"] == 2
    assert db_session.query(DeviceUserDrift).filter_by(status="open").count() == 0


@pytest.mark.testid("BE-UNIT-DRIFT-002")
def test_mark_drift_resolved(db_session) -> None:
    persist_drift_events(db_session, device_id="gate-1", missing_on_device=["9"], missing_mapping=[])
    db_session.commit()
    row = db_session.query(DeviceUserDrift).first()
    updated = mark_drift_resolved(db_session, row.id, resolution="manual", command_uuid="abc")
    db_session.commit()
    assert updated is not None
    assert updated.status == "resolved"
    assert updated.command_uuid == "abc"
