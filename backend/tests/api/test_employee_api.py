"""API tests for /employees* endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_header_for
from tests.factories import make_employee, make_user


EMPLOYEE_PAYLOAD = {
    "device_user_id": "TBI1001",
    "name": "Ada Lovelace",
    "department": "Engineering",
    "shift_start": "09:00:00",
    "shift_end": "18:00:00",
}


@pytest.mark.testid("BE-API-EMP-001")
def test_list_employees_empty(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/employees", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.testid("BE-API-EMP-003")
def test_create_employee(client: TestClient, admin_headers: dict[str, str]) -> None:
    with patch("app.domains.employees.router.process_command"):
        response = client.post("/employees", headers=admin_headers, json=EMPLOYEE_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["device_user_id"] == "TBI1001"
    assert body["name"] == "Ada Lovelace"
    assert body["department"] == "Engineering"
    assert body["shift_start"] in {"09:00:00", "09:00"}
    assert body["shift_end"] in {"18:00:00", "18:00"}
    assert body["id"] > 0


@pytest.mark.testid("BE-API-EMP-002")
def test_get_employee_by_id(client: TestClient, admin_headers: dict[str, str], db_session: Session) -> None:
    emp = make_employee(device_user_id="TBI2002", name="Grace Hopper")
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    response = client.get(f"/employees/{emp.id}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == emp.id
    assert body["device_user_id"] == "TBI2002"
    assert "total_logs" in body


@pytest.mark.testid("BE-API-EMP-004")
def test_update_employee_department(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    emp = make_employee(device_user_id="TBI3003", department="Sales")
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    with patch("app.domains.employees.router.process_command"):
        response = client.put(
            f"/employees/{emp.id}",
            headers=admin_headers,
            json={"department": "People Ops"},
        )
    assert response.status_code == 200
    assert response.json()["department"] == "People Ops"


@pytest.mark.testid("BE-API-EMP-006")
def test_employee_daily_attendance(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    emp = make_employee(device_user_id="TBI4004")
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)

    response = client.get(
        f"/employees/{emp.id}/daily-attendance",
        headers=admin_headers,
        params={"from": "2026-07-01", "to": "2026-07-03"},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 3
    assert all("summary_date" in row and "absent" in row for row in body)


@pytest.mark.testid("BE-API-EMP-005")
def test_delete_offboard_employee(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    emp = make_employee(device_user_id="TBI5005")
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    emp_id = emp.id

    with (
        patch("app.domains.employees.services.employee_offboard_service.process_command"),
        patch("app.domains.employees.services.employee_offboard_service.device_service_for") as svc_for,
    ):
        svc_for.return_value.resolve_uid_for_user_id.return_value = 1
        response = client.delete(f"/employees/{emp_id}", headers=admin_headers)
    assert response.status_code == 204

    listed = client.get("/employees", headers=admin_headers)
    assert listed.status_code == 200
    assert all(row["id"] != emp_id for row in listed.json())


@pytest.mark.testid("BE-API-EMP-007")
def test_delete_forbidden_without_edit(client: TestClient, db_session: Session) -> None:
    """CEO has EMPLOYEE_VIEW but not EMPLOYEE_EDIT (HR_ADMIN currently has edit)."""
    emp = make_employee(device_user_id="TBI6006")
    db_session.add(emp)
    ceo = make_user(email="ceo@example.com", role="CEO", full_name="CEO User")
    db_session.add(ceo)
    db_session.commit()
    db_session.refresh(emp)

    response = client.delete(f"/employees/{emp.id}", headers=auth_header_for(ceo))
    assert response.status_code == 403
