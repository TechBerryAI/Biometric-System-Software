"""Fleet device management API tests."""

from __future__ import annotations

from tests.factories import make_device


def test_list_devices_empty(client, admin_headers):
    response = client.get("/devices", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_device(client, admin_headers, db_session):
    response = client.post(
        "/devices",
        headers=admin_headers,
        json={
            "name": "branch-a-entrance",
            "ip_address": "192.168.1.201",
            "port": 4370,
            "branch_id": "branch-a",
            "connectivity_mode": "pull",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "branch-a-entrance"
    assert body["branch_id"] == "branch-a"
    assert body["health_status"] == "UNKNOWN"

    get_response = client.get("/devices/branch-a-entrance", headers=admin_headers)
    assert get_response.status_code == 200
    assert get_response.json()["ip_address"] == "192.168.1.201"


def test_create_duplicate_device_conflict(client, admin_headers, db_session):
    device = make_device(name="dup-device")
    db_session.add(device)
    db_session.commit()
    response = client.post(
        "/devices",
        headers=admin_headers,
        json={"name": "dup-device", "ip_address": "192.168.1.202"},
    )
    assert response.status_code == 409


def test_device_health_endpoint(client, admin_headers, db_session):
    device = make_device(name="health-device", health_status="ONLINE")
    db_session.add(device)
    db_session.commit()
    response = client.get("/devices/health-device/health", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["device_id"] == "health-device"
    assert body["health_status"] == "ONLINE"


def test_enqueue_device_command(client, admin_headers, db_session):
    device = make_device(name="cmd-device")
    db_session.add(device)
    db_session.commit()
    response = client.post(
        "/devices/cmd-device/commands",
        headers=admin_headers,
        json={"command_type": "FIRMWARE_CHECK", "payload": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["command_type"] == "FIRMWARE_CHECK"
    assert body["status"] == "PENDING"
