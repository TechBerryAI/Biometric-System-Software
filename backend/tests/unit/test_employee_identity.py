"""Unit tests for employee identity filters."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.employees.services.employee_identity import identity_filter_for_employee
from tests.factories import make_attendance_log, make_employee, make_mapping


@pytest.mark.testid("BE-UNIT-IDENT-001")
def test_identity_filter_for_employee(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBI001", name="Unmesh Tari")
    db_session.add(emp)
    db_session.flush()
    db_session.add(make_mapping(employee=emp, device_id="main-entrance"))
    own = make_attendance_log(employee=emp, punch_type="0")
    other = make_employee(device_user_id="TBI174", name="Other")
    db_session.add(other)
    db_session.flush()
    foreign = make_attendance_log(employee=other, punch_type="0")
    db_session.add_all([own, foreign])
    db_session.commit()

    filt = identity_filter_for_employee(emp, db_session)
    rows = list(db_session.execute(select(AttendanceLog).where(filt)).scalars().all())
    assert len(rows) == 1
    assert rows[0].employee_code == "TBI001"
