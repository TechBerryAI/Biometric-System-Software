"""Unit tests for employee department / shift factory fields."""

from __future__ import annotations

from datetime import time

import pytest
from sqlalchemy.orm import Session

from tests.factories import make_employee


@pytest.mark.testid("BE-UNIT-EMP-DEPT-001")
def test_employee_factory_has_department_and_shift_times(db_session: Session) -> None:
    emp = make_employee(
        device_user_id="TBI001",
        name="Unmesh Tari",
        department="Engineering",
        shift_start=time(9, 0),
        shift_end=time(18, 0),
    )
    assert emp.department == "Engineering"
    assert emp.shift_start == time(9, 0)
    assert emp.shift_end == time(18, 0)

    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    assert emp.department == "Engineering"
    assert emp.shift_start == time(9, 0)
    assert emp.shift_end == time(18, 0)
