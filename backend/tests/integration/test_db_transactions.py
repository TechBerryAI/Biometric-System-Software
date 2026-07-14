"""Integration: session rollback leaves no persisted rows."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.employees.models.employee import Employee
from tests.factories import make_employee


@pytest.mark.integration
@pytest.mark.testid("BE-INT-TXN-001")
def test_rollback_discards_uncommitted_employee(db_session: Session) -> None:
    emp = make_employee(device_user_id="TBITXN1", name="Rollback Target")
    db_session.add(emp)
    db_session.flush()
    assert emp.id is not None

    db_session.rollback()

    count = db_session.execute(select(func.count()).select_from(Employee)).scalar_one()
    assert count == 0
