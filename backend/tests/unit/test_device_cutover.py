"""Unit tests for replacement-hardware cutover gates and dry-run planning."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domains.devices.cutover import (
    RETIRED_PRIMARY_IP,
    RETIRED_PRIMARY_SERIAL,
    ReplacementHardwareError,
    assert_replacement_hardware,
    replacement_hardware_ready,
)
from app.domains.devices.services.device_migration_service import next_free_uid, plan_actions
from app.domains.devices.services.device_service import DeviceService
from tests.factories import make_device, make_employee


def test_gate_allows_previous_lan_address_when_serial_is_new() -> None:
    device = make_device(name="main-entrance", ip_address=RETIRED_PRIMARY_IP)
    device.serial_number = "JJA1261800763"
    ok, reason = replacement_hardware_ready(device, require_serial=True)
    assert ok is True
    assert reason is None


def test_gate_allows_previous_lan_address_before_serial_is_known() -> None:
    device = make_device(name="main-entrance", ip_address=RETIRED_PRIMARY_IP)
    ok, reason = replacement_hardware_ready(device, require_serial=False)
    assert ok is True
    assert reason is None


def test_gate_blocks_retired_serial() -> None:
    device = make_device(name="main-entrance", ip_address="192.168.1.180")
    device.serial_number = RETIRED_PRIMARY_SERIAL
    with pytest.raises(ReplacementHardwareError, match=RETIRED_PRIMARY_SERIAL):
        assert_replacement_hardware(device)


def test_gate_allows_new_ip_and_serial() -> None:
    device = make_device(name="main-entrance", ip_address="192.168.1.180")
    ok, reason = replacement_hardware_ready(device, serial="NEWBOX123", require_serial=True)
    assert ok is True
    assert reason is None


def test_next_free_uid_preserves_preferred() -> None:
    assert next_free_uid({1, 2}, 5) == 5
    assert next_free_uid({1, 2, 5}, 5) == 3


def test_plan_actions_create_skip_conflict() -> None:
    create_emp = make_employee(device_user_id="TBI001", name="Ada", device_uid=3)
    create_emp.id = 1
    skip_emp = make_employee(device_user_id="TBI002", name="Grace", device_uid=4)
    skip_emp.id = 2
    skip_emp.device_privilege = 0
    conflict_emp = make_employee(device_user_id="TBI003", name="Expected", device_uid=5)
    conflict_emp.id = 3
    snapshot = {
        "users": [
            {"user_id": "TBI002", "name": "Grace", "uid": 4, "privilege": 0, "group_id": None, "card": "0"},
            {"user_id": "TBI003", "name": "Other", "uid": 9, "privilege": 0, "group_id": None, "card": "0"},
        ],
        "user_count": 2,
    }
    rows = plan_actions([create_emp, skip_emp, conflict_emp], snapshot)
    by_id = {row["device_user_id"]: row for row in rows}
    assert by_id["TBI001"]["action"] == "CREATE"
    assert by_id["TBI001"]["uid"] == 3
    assert by_id["TBI002"]["action"] == "SKIP"
    assert by_id["TBI003"]["action"] == "CONFLICT"


def test_upsert_user_omits_uid_when_unknown() -> None:
    captured: dict = {}
    adapter = MagicMock()

    def run(_op, callback, max_attempts=2):
        conn = MagicMock()
        conn.get_users.return_value = []

        def set_user(**kwargs):
            captured.update(kwargs)

        conn.set_user.side_effect = set_user
        return callback(conn)

    adapter.run.side_effect = run
    service = DeviceService.__new__(DeviceService)
    service._settings = MagicMock()
    service._connection = MagicMock()
    service._adapter = adapter
    service.upsert_user(user_id="TBI1", name="Ada")
    assert "uid" not in captured
    assert captured["user_id"] == "TBI1"
    assert captured["name"] == "Ada"


def test_create_missing_users_skips_existing_and_avoids_dangerous_methods() -> None:
    seen: dict[str, MagicMock] = {}
    adapter = MagicMock()
    existing = MagicMock(uid=2, user_id="TBI002", name="Grace")

    def run(_op, callback, max_attempts=2):
        conn = MagicMock()
        conn.get_users.side_effect = [[existing], [existing, MagicMock(uid=1, user_id="TBI001", name="Ada")]]
        seen["conn"] = conn
        return callback(conn)

    adapter.run.side_effect = run
    service = DeviceService.__new__(DeviceService)
    service._settings = MagicMock()
    service._connection = MagicMock(ip_address="192.168.1.119", port=4370)
    service._adapter = adapter
    result = service.create_missing_users(
        [
            {"user_id": "TBI002", "name": "Grace", "uid": 2, "privilege": 0, "group_id": "", "card": "0"},
            {"user_id": "TBI001", "name": "Ada", "uid": 1, "privilege": 0, "group_id": "", "card": "0"},
        ]
    )
    conn = seen["conn"]
    conn.delete_user.assert_not_called()
    conn.clear_data.assert_not_called()
    conn.clear_attendance.assert_not_called()
    assert result["skipped"][0]["user_id"] == "TBI002"
    assert result["created"][0]["user_id"] == "TBI001"
    conn.set_user.assert_called_once()
    seen: dict[str, MagicMock] = {}
    adapter = MagicMock()

    def run(_op, callback, max_attempts=2):
        conn = MagicMock()
        conn.get_firmware_version.return_value = "Ver 1"
        conn.get_serialnumber.return_value = "NEWBOX123"
        conn.get_platform.return_value = "ZMM"
        conn.get_fp_version.return_value = 10
        conn.get_face_version.side_effect = Exception("no face")
        conn.get_users.return_value = []
        seen["conn"] = conn
        return callback(conn)

    adapter.run.side_effect = run
    service = DeviceService.__new__(DeviceService)
    service._settings = MagicMock()
    service._connection = MagicMock(ip_address="192.168.1.180", port=4370)
    service._adapter = adapter
    service.probe_tcp_connection = MagicMock(return_value=(True, "tcp_connected"))
    snapshot = service.inspect_readonly()
    assert snapshot["connected"] is True
    assert snapshot["serial_number"] == "NEWBOX123"
    conn = seen["conn"]
    conn.clear_attendance.assert_not_called()
    conn.clear_data.assert_not_called()
    conn.delete_user.assert_not_called()
    conn.set_user.assert_not_called()
    conn.restart.assert_not_called()
