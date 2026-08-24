"""API tests for /attendance* endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_session import AttendanceSession
from tests.factories import make_attendance_log, make_employee

UTC = ZoneInfo("UTC")


@pytest.fixture()
def seeded_attendance(db_session: Session):
    emp = make_employee(device_user_id="TBIATT01", name="Attendance Probe")
    db_session.add(emp)
    db_session.flush()
    check_in = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    check_out = check_in + timedelta(hours=8)
    log_in = make_attendance_log(employee=emp, punched_at=check_in, punch_type="0")
    log_out = make_attendance_log(employee=emp, punched_at=check_out, punch_type="1")
    session = AttendanceSession(
        employee_id=emp.id,
        check_in=check_in,
        check_out=check_out,
        work_duration=480,
        status="complete",
    )
    db_session.add_all([log_in, log_out, session])
    db_session.commit()
    db_session.refresh(emp)
    return emp, check_in.date()


@pytest.mark.testid("BE-API-ATT-001")
def test_list_attendance_logs(
    client: TestClient, admin_headers: dict[str, str], seeded_attendance
) -> None:
    emp, day = seeded_attendance
    response = client.get(
        "/attendance/logs",
        headers=admin_headers,
        params={"from": day.isoformat(), "to": day.isoformat(), "employee_id": emp.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["employee_code"] == emp.device_user_id


@pytest.mark.testid("BE-API-ATT-002")
def test_list_attendance_sessions(
    client: TestClient, admin_headers: dict[str, str], seeded_attendance
) -> None:
    emp, day = seeded_attendance
    response = client.get(
        "/attendance/sessions",
        headers=admin_headers,
        params={"from": day.isoformat(), "to": day.isoformat(), "employee_id": emp.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["employee_id"] == emp.id


@pytest.mark.testid("BE-API-ATT-003")
def test_daily_summary(
    client: TestClient, admin_headers: dict[str, str], seeded_attendance
) -> None:
    _emp, day = seeded_attendance
    response = client.get(
        "/attendance/daily-summary",
        headers=admin_headers,
        params={"summary_date": day.isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body
    assert "summary_date" in body[0]
    assert "employee_id" in body[0]
    assert "first_check_in" in body[0]
    assert "last_check_out" in body[0]
    assert "total_work_minutes" in body[0]
    assert "sessions_count" in body[0]


@pytest.mark.testid("BE-API-ATT-006")
def test_attendance_clock(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/attendance/clock", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "timezone" in body
    assert "local_today" in body
    assert "employee_id" not in body


@pytest.mark.testid("BE-API-ATT-004")
def test_daily_summary_range(
    client: TestClient, admin_headers: dict[str, str], seeded_attendance
) -> None:
    _emp, day = seeded_attendance
    response = client.get(
        "/attendance/daily-summary/range",
        headers=admin_headers,
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert day.isoformat() in body


@pytest.mark.testid("BE-API-ATT-005")
def test_attendance_by_employee_id(
    client: TestClient, admin_headers: dict[str, str], seeded_attendance
) -> None:
    emp, day = seeded_attendance
    response = client.get(
        f"/attendance/{emp.id}",
        headers=admin_headers,
        params={"from": day.isoformat(), "to": day.isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["employee_id"] == emp.id
