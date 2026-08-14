"""Unit tests for ReportingService."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.reporting.services.reporting_service import ReportingService
from tests.factories import make_attendance_log, make_device, make_employee

UTC = ZoneInfo("UTC")


@pytest.mark.testid("BE-UNIT-REPORT-001")
def test_reporting_heatmap_counts_punches(db_session: Session) -> None:
    emp = make_employee(device_user_id="HEAT001")
    db_session.add(emp)
    db_session.flush()
    ts = datetime.now(UTC)
    db_session.add(make_attendance_log(employee=emp, punched_at=ts, punch_type="0"))
    db_session.commit()

    service = ReportingService(get_settings())
    result = service.attendance_heatmap(db_session, days=7)
    assert result.cells
    assert sum(cell.punch_count for cell in result.cells) >= 1


@pytest.mark.testid("BE-UNIT-REPORT-002")
def test_reporting_branch_comparison_groups_by_department(db_session: Session) -> None:
    emp_a = make_employee(device_user_id="BR001", department="Sales")
    emp_b = make_employee(device_user_id="BR002", department="Engineering")
    db_session.add_all([emp_a, emp_b])
    db_session.commit()

    service = ReportingService(get_settings())
    result = service.branch_comparison(db_session, days=7)
    branch_ids = {row.branch_id for row in result.branches}
    assert "sales" in branch_ids
    assert "engineering" in branch_ids


@pytest.mark.testid("BE-UNIT-REPORT-003")
def test_reporting_device_uptime_returns_active_devices(db_session: Session) -> None:
    device = make_device(name="uptime-gate", health_status="ONLINE")
    device.last_seen = datetime.now(UTC)
    db_session.add(device)
    db_session.commit()

    service = ReportingService(get_settings())
    result = service.device_uptime(db_session, days=7)
    assert len(result.devices) == 1
    assert result.devices[0].uptime_percent >= 0
