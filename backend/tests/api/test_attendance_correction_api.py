"""API tests for /attendance/adjust* endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.attendance.services.attendance_correction_service import (
    CORRECTION_STATUS_APPLIED,
    AttendanceAdjustmentResult,
)
from tests.factories import make_attendance_log, make_device_command, make_employee

UTC = ZoneInfo("UTC")


@pytest.fixture()
def adjust_employee(db_session: Session):
    emp = make_employee(device_user_id="TBIADJ01", name="Adjust Target")
    db_session.add(emp)
    db_session.flush()
    day = date.today()
    check_in = datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)
    check_out = check_in + timedelta(hours=8)
    db_session.add(make_attendance_log(employee=emp, punched_at=check_in, punch_type="0"))
    db_session.add(make_attendance_log(employee=emp, punched_at=check_out, punch_type="1"))
    db_session.commit()
    db_session.refresh(emp)
    return emp, day


@pytest.mark.testid("BE-API-ADJ-001")
def test_correction_capabilities(client: TestClient, operator_headers: dict[str, str]) -> None:
    fake_caps = {
        "tier": "A",
        "record_size": 40,
        "supports_selective_delete": True,
        "supports_full_rewrite": True,
        "supports_write": True,
    }
    with patch(
        "app.domains.attendance.correction_router.probe_correction_capabilities",
        return_value=fake_caps,
    ):
        response = client.get("/attendance/adjust/capabilities", headers=operator_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "A"
    assert body["supports_write"] is True
    assert body["record_size"] == 40


@pytest.mark.testid("BE-API-ADJ-002")
def test_correction_command_status(
    client: TestClient, operator_headers: dict[str, str], db_session: Session, adjust_employee
) -> None:
    emp, day = adjust_employee
    missing = client.get(
        "/attendance/adjust/commands/cmd_0000000000000000",
        headers=operator_headers,
    )
    assert missing.status_code == 404

    cmd = make_device_command(
        command_type="CORRECT_ATTENDANCE",
        payload={
            "employee_id": emp.id,
            "local_date": day.isoformat(),
            "new_check_in": datetime(day.year, day.month, day.day, 9, 15, tzinfo=UTC).isoformat(),
            "new_check_out": datetime(day.year, day.month, day.day, 17, 45, tzinfo=UTC).isoformat(),
        },
        status="PENDING",
    )
    db_session.add(cmd)
    db_session.commit()

    response = client.get(
        f"/attendance/adjust/commands/{cmd.command_uuid}",
        headers=operator_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["device_command_uuid"] == cmd.command_uuid
    assert body["employee_id"] == emp.id
    assert body["status"] == "device_pending"


@pytest.mark.testid("BE-API-ADJ-003")
def test_day_preview(
    client: TestClient, operator_headers: dict[str, str], adjust_employee
) -> None:
    emp, day = adjust_employee
    response = client.get(
        f"/attendance/adjust/day/{emp.id}",
        headers=operator_headers,
        params={"date": day.isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["employee_id"] == emp.id
    assert body["local_date"] == day.isoformat()
    assert body["punch_count"] >= 1


@pytest.mark.testid("BE-API-ADJ-004")
def test_correct_endpoint(
    client: TestClient, operator_headers: dict[str, str], adjust_employee
) -> None:
    emp, day = adjust_employee
    new_in = datetime(day.year, day.month, day.day, 9, 30, tzinfo=UTC)
    new_out = datetime(day.year, day.month, day.day, 17, 30, tzinfo=UTC)
    fake_result = AttendanceAdjustmentResult(
        employee_id=emp.id,
        local_date=day,
        previous_check_in=new_in - timedelta(minutes=30),
        previous_check_out=new_out + timedelta(minutes=30),
        new_check_in=new_in,
        new_check_out=new_out,
        status=CORRECTION_STATUS_APPLIED,
        device_updated=True,
        device_command_uuid="cmd-fake-uuid",
        device_tier="A",
        error_message=None,
        applied_at=datetime.now(UTC),
    )
    with patch(
        "app.domains.attendance.correction_router.apply_attendance_correction",
        return_value=fake_result,
    ):
        response = client.post(
            "/attendance/adjust/correct",
            headers=operator_headers,
            json={
                "employee_id": emp.id,
                "local_date": day.isoformat(),
                "new_check_in": new_in.isoformat(),
                "new_check_out": new_out.isoformat(),
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["employee_id"] == emp.id
    assert body["status"] == CORRECTION_STATUS_APPLIED
    assert body["device_updated"] is True


@pytest.mark.testid("BE-API-ADJ-004")
def test_correct_endpoint_mark_absent(
    client: TestClient, operator_headers: dict[str, str], adjust_employee
) -> None:
    emp, day = adjust_employee
    fake_result = AttendanceAdjustmentResult(
        employee_id=emp.id,
        local_date=day,
        previous_check_in=datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC),
        previous_check_out=datetime(day.year, day.month, day.day, 17, 0, tzinfo=UTC),
        new_check_in=None,
        new_check_out=None,
        status=CORRECTION_STATUS_APPLIED,
        device_updated=False,
        device_command_uuid="cmd-absent-uuid",
        device_tier="C",
        error_message=None,
        applied_at=datetime.now(UTC),
    )
    with patch(
        "app.domains.attendance.correction_router.apply_attendance_correction",
        return_value=fake_result,
    ) as apply_mock:
        response = client.post(
            "/attendance/adjust/correct",
            headers=operator_headers,
            json={
                "employee_id": emp.id,
                "local_date": day.isoformat(),
                "new_check_in": None,
                "new_check_out": None,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == CORRECTION_STATUS_APPLIED
    assert body["new_check_in"] is None
    assert body["new_check_out"] is None
    assert apply_mock.call_args.kwargs["new_check_in"] is None
    assert apply_mock.call_args.kwargs["new_check_out"] is None


@pytest.mark.testid("BE-API-ADJ-005")
def test_correct_forbidden_for_non_operator(
    client: TestClient, hr_headers: dict[str, str], adjust_employee
) -> None:
    emp, day = adjust_employee
    new_in = datetime(day.year, day.month, day.day, 9, 30, tzinfo=UTC)
    response = client.post(
        "/attendance/adjust/correct",
        headers=hr_headers,
        json={
            "employee_id": emp.id,
            "local_date": day.isoformat(),
            "new_check_in": new_in.isoformat(),
        },
    )
    assert response.status_code == 403
