"""E2E scenario: company operations day (bootstrap → employee → summary → offboard)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


EMPLOYEE_PAYLOAD = {
    "device_user_id": "TBISCN01",
    "name": "Scenario Employee",
    "department": "Operations",
    "shift_start": "09:00:00",
    "shift_end": "18:00:00",
}


@pytest.mark.slow
@pytest.mark.testid("BE-SCN-DAY-001")
def test_company_operations_day(client: TestClient, db_session: Session) -> None:
    # 1) Bootstrap admin
    bootstrap = client.post("/auth/bootstrap-admin")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["email"] == "bootstrap@example.com"

    # 2) Login
    login = client.post(
        "/auth/login",
        json={"email": "bootstrap@example.com", "password": "Bootstrap123!"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # 3) Create employee (patch device upsert processing)
    with patch("app.domains.employees.router.process_command"):
        create = client.post("/employees", headers=headers, json=EMPLOYEE_PAYLOAD)
    assert create.status_code == 200
    employee = create.json()
    assert employee["device_user_id"] == "TBISCN01"
    employee_id = employee["id"]

    # 4) List employees
    listed = client.get("/employees", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == employee_id for row in listed.json())

    # 5) Daily summary (empty-ish but reachable)
    today = date.today().isoformat()
    summary = client.get(
        "/attendance/daily-summary",
        headers=headers,
        params={"summary_date": today},
    )
    assert summary.status_code == 200
    assert isinstance(summary.json(), list)

    # 6) Offboard / delete employee
    with (
        patch("app.domains.employees.services.employee_offboard_service.process_command"),
        patch("app.domains.employees.services.employee_offboard_service.DeviceService") as device_cls,
    ):
        device_cls.return_value.resolve_uid_for_user_id.return_value = 1
        deleted = client.delete(f"/employees/{employee_id}", headers=headers)
    assert deleted.status_code == 204

    listed_after = client.get("/employees", headers=headers)
    assert listed_after.status_code == 200
    assert all(row["id"] != employee_id for row in listed_after.json())
