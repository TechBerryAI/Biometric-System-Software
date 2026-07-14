"""Integration: employee soft-offboard sets departed_at."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.domains.employees.services.employee_offboard_service import offboard_employee
from tests.factories import make_control_state, make_employee, make_mapping, make_user


@pytest.mark.integration
@pytest.mark.testid("BE-INT-OFF-001")
@pytest.mark.testid("BE-INT-MDL-004")
def test_offboard_employee_sets_departed_at(db_session: Session) -> None:
    actor = make_user(email="offboard-actor@example.com")
    emp = make_employee(device_user_id="TBIOFF1", name="Departing User")
    db_session.add_all([actor, emp])
    db_session.flush()
    db_session.add(make_mapping(employee=emp))
    db_session.add(make_control_state())
    db_session.commit()
    db_session.refresh(emp)
    db_session.refresh(actor)

    with (
        patch("app.domains.employees.services.employee_offboard_service.DeviceService") as device_cls,
        patch("app.domains.employees.services.employee_offboard_service.process_command"),
    ):
        device_cls.return_value.resolve_uid_for_user_id.return_value = 1
        device_cls.return_value = MagicMock(resolve_uid_for_user_id=MagicMock(return_value=1))
        applied = offboard_employee(
            db_session,
            emp,
            actor_user_uuid=actor.user_uuid,
            process_device_inline=True,
        )
        db_session.commit()

    assert applied is True
    db_session.refresh(emp)
    assert emp.departed_at is not None
