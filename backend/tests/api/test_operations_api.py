"""API tests for /ops* endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.devices.models.device_command import DeviceCommandStatus
from tests.factories import make_device_command


@pytest.mark.testid("BE-API-OPS-003")
def test_ops_metrics(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/ops/metrics", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "queue_depth" in body
    assert "device_health_status" in body
    assert "device_ip" in body
    assert "device_port" in body


@pytest.mark.testid("BE-API-OPS-001")
def test_list_device_commands(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    cmd = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBI001", "name": "Ops Test"},
        status=DeviceCommandStatus.PENDING.value,
    )
    db_session.add(cmd)
    db_session.commit()

    response = client.get("/ops/device-commands", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert any(row["command_uuid"] == cmd.command_uuid for row in body)


@pytest.mark.testid("BE-API-OPS-002")
def test_process_device_command(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    cmd = make_device_command(
        command_type="UPSERT_USER",
        payload={"user_id": "TBI002", "name": "Process Me"},
        status=DeviceCommandStatus.PENDING.value,
    )
    db_session.add(cmd)
    db_session.commit()
    db_session.refresh(cmd)

    def _fake_reprocess(db: Session, command_uuid: str, **_kwargs):
        cmd.status = DeviceCommandStatus.SUCCESS.value
        db.add(cmd)
        db.flush()
        return cmd

    with patch(
        "app.domains.ops.router.reprocess_device_command",
        side_effect=_fake_reprocess,
    ):
        response = client.post(
            f"/ops/device-commands/{cmd.command_uuid}/process",
            headers=admin_headers,
        )
    assert response.status_code == 200
    assert response.json()["command_uuid"] == cmd.command_uuid
    assert response.json()["status"] == DeviceCommandStatus.SUCCESS.value
