"""API tests for replacement device inspect and metadata migration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.factories import make_control_state, make_device, make_employee, make_mapping


def _replacement_device(**kwargs):
    device = make_device(
        name="main-entrance",
        ip_address=kwargs.pop("ip_address", "192.168.1.180"),
        connectivity_mode="both",
        **kwargs,
    )
    device.serial_number = "NEWBOX123"
    device.capabilities = {
        "last_inspect": {
            "connected": True,
            "serial_number": "NEWBOX123",
            "replacement_confirmed": True,
            "users": [],
            "user_count": 0,
        }
    }
    return device


def test_inspect_allowed_at_previous_lan_address(client, admin_headers, db_session):
    device = make_device(name="main-entrance", ip_address="192.168.1.119", connectivity_mode="both")
    db_session.add(device)
    db_session.commit()
    snapshot = {
        "connected": True,
        "connection_detail": "connected",
        "firmware_version": "Ver X",
        "serial_number": "JJA1261800763",
        "platform": "ZMM",
        "fp_version": "10",
        "face_version": None,
        "users": [],
        "user_count": 0,
        "unsupported": [],
        "errors": {},
    }
    with (
        patch("app.domains.devices.services.device_migration_service.device_session_lock") as lock,
        patch("app.domains.devices.services.device_migration_service.device_service_for") as svc_for,
    ):
        lock.return_value.__enter__ = MagicMock()
        lock.return_value.__exit__ = MagicMock(return_value=False)
        svc_for.return_value.inspect_readonly.return_value = snapshot
        response = client.post("/devices/main-entrance/inspect", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["serial_number"] == "JJA1261800763"
    assert body["replacement_confirmed"] is True


def test_inspect_marks_retired_serial_unconfirmed(client, admin_headers, db_session):
    device = make_device(name="main-entrance", ip_address="192.168.1.119", connectivity_mode="both")
    db_session.add(device)
    db_session.commit()
    snapshot = {
        "connected": True,
        "connection_detail": "connected",
        "firmware_version": "Ver X",
        "serial_number": "JJA1240500503",
        "platform": "ZMM",
        "fp_version": "10",
        "face_version": None,
        "users": [],
        "user_count": 0,
        "unsupported": [],
        "errors": {},
    }
    with (
        patch("app.domains.devices.services.device_migration_service.device_session_lock") as lock,
        patch("app.domains.devices.services.device_migration_service.device_service_for") as svc_for,
    ):
        lock.return_value.__enter__ = MagicMock()
        lock.return_value.__exit__ = MagicMock(return_value=False)
        svc_for.return_value.inspect_readonly.return_value = snapshot
        response = client.post("/devices/main-entrance/inspect", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["replacement_confirmed"] is False
    assert "JJA1240500503" in (body.get("replacement_blocker") or "")


def test_inspect_persists_snapshot(client, admin_headers, db_session):
    device = make_device(name="main-entrance", ip_address="192.168.1.180", connectivity_mode="both")
    db_session.add(device)
    db_session.commit()
    snapshot = {
        "connected": True,
        "connection_detail": "connected",
        "firmware_version": "Ver X",
        "serial_number": "NEWBOX123",
        "platform": "ZMM",
        "fp_version": "10",
        "face_version": None,
        "users": [],
        "user_count": 0,
        "unsupported": [],
        "errors": {},
    }
    with (
        patch("app.domains.devices.services.device_migration_service.device_session_lock") as lock,
        patch("app.domains.devices.services.device_migration_service.device_service_for") as svc_for,
    ):
        lock.return_value.__enter__ = MagicMock()
        lock.return_value.__exit__ = MagicMock(return_value=False)
        svc_for.return_value.inspect_readonly.return_value = snapshot
        response = client.post("/devices/main-entrance/inspect", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["serial_number"] == "NEWBOX123"
    assert body["replacement_confirmed"] is True
    db_session.refresh(device)
    assert device.serial_number == "NEWBOX123"
    assert device.capabilities["last_inspect"]["serial_number"] == "NEWBOX123"


def test_preflight_and_dry_run(client, admin_headers, db_session):
    device = _replacement_device()
    emp = make_employee(device_user_id="TBI001", name="Ada", device_uid=3)
    db_session.add_all([device, emp, make_control_state()])
    db_session.flush()
    db_session.add(make_mapping(employee=emp))
    db_session.commit()

    pre = client.post("/devices/main-entrance/migration/preflight", headers=admin_headers, json={})
    assert pre.status_code == 200
    summary = pre.json()["preflight_summary"]
    assert summary["total_employees_in_scope"] == 1
    assert summary["create"] == 1

    dry = client.post("/devices/main-entrance/migration/dry-run", headers=admin_headers, json={})
    assert dry.status_code == 200
    items = dry.json()["items"]
    assert items[0]["action"] == "CREATE"
    assert items[0]["device_user_id"] == "TBI001"


def test_execute_refuses_retired_serial(client, admin_headers, db_session):
    device = _replacement_device(ip_address="192.168.1.119")
    device.serial_number = "JJA1240500503"
    device.capabilities = {
        "last_inspect": {
            "connected": True,
            "serial_number": "JJA1240500503",
            "replacement_confirmed": False,
            "users": [],
            "user_count": 0,
        }
    }
    db_session.add_all([device, make_control_state()])
    db_session.commit()
    response = client.post("/devices/main-entrance/migration/dry-run", headers=admin_headers, json={})
    assert response.status_code == 409
    assert "JJA1240500503" in response.json()["detail"]


def test_execute_allows_previous_lan_address_with_new_serial(client, admin_headers, db_session):
    device = _replacement_device(ip_address="192.168.1.119")
    emp = make_employee(device_user_id="TBI001", name="Ada", device_uid=3)
    db_session.add_all([device, emp, make_control_state()])
    db_session.flush()
    db_session.add(make_mapping(employee=emp))
    db_session.commit()
    dry = client.post("/devices/main-entrance/migration/dry-run", headers=admin_headers, json={})
    migration_id = dry.json()["migration_id"]
    with (
        patch("app.domains.devices.services.device_migration_service.device_session_lock") as lock,
        patch("app.domains.devices.services.device_migration_service.device_service_for") as svc_for,
    ):
        lock.return_value.__enter__ = MagicMock()
        lock.return_value.__exit__ = MagicMock(return_value=False)
        svc_for.return_value.fetch_users.return_value = []
        svc_for.return_value.create_missing_users.return_value = {
            "created": [{"user_id": "TBI001", "uid": 3}],
            "skipped": [],
            "failed": [],
            "users": [{"user_id": "TBI001", "uid": 3, "name": "Ada"}],
        }
        response = client.post(
            "/devices/main-entrance/migration/execute",
            headers=admin_headers,
            json={
                "dry_run_id": migration_id,
                "confirm_target_device_name": "main-entrance",
                "confirm_target_ip": "192.168.1.119",
            },
        )
    assert response.status_code == 200, response.text


def test_execute_creates_user_and_updates_uid(client, admin_headers, db_session):
    device = _replacement_device()
    emp = make_employee(device_user_id="TBI001", name="Ada", device_uid=3)
    db_session.add_all([device, emp, make_control_state()])
    db_session.flush()
    db_session.add(make_mapping(employee=emp))
    db_session.commit()

    dry = client.post("/devices/main-entrance/migration/dry-run", headers=admin_headers, json={})
    migration_id = dry.json()["migration_id"]

    with (
        patch("app.domains.devices.services.device_migration_service.device_session_lock") as lock,
        patch("app.domains.devices.services.device_migration_service.device_service_for") as svc_for,
    ):
        lock.return_value.__enter__ = MagicMock()
        lock.return_value.__exit__ = MagicMock(return_value=False)
        svc_for.return_value.fetch_users.return_value = []
        svc_for.return_value.create_missing_users.return_value = {
            "created": [{"user_id": "TBI001", "uid": 3}],
            "skipped": [],
            "failed": [],
            "users": [{"user_id": "TBI001", "uid": 3, "name": "Ada"}],
        }
        response = client.post(
            "/devices/main-entrance/migration/execute",
            headers=admin_headers,
            json={
                "dry_run_id": migration_id,
                "confirm_target_device_name": "main-entrance",
                "confirm_target_ip": "192.168.1.180",
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] in {"VERIFIED", "PARTIAL"}
    db_session.refresh(emp)
    assert emp.device_uid == 3
    report = client.get(
        f"/devices/main-entrance/migration/{migration_id}/report",
        headers=admin_headers,
    )
    assert report.status_code == 200
    assert "enroll fingerprints" in report.json()["fingerprint_next_step"].lower()
