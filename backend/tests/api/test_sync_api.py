"""API tests for /sync* endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@contextmanager
def _noop_lock(*_args, **_kwargs):
    yield


@pytest.mark.testid("BE-API-SYNC-001")
def test_sync_device_success(client: TestClient, admin_headers: dict[str, str]) -> None:
    cache = MagicMock()
    with (
        patch("app.domains.devices.router.wait_for_correction_commands_clear", return_value=True),
        patch("app.domains.devices.router.device_session_lock", side_effect=_noop_lock),
        patch("app.domains.devices.router.run_user_sync", return_value=(12, 2)),
        patch("app.domains.devices.router.run_device_sync", return_value=(40, 5, 1)) as device_sync,
        patch("app.domains.devices.router.update_device_health"),
        patch("app.domains.devices.router.AIResponseCache", return_value=cache),
    ):
        response = client.post("/sync/device", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["users_on_device"] == 12
    assert body["new_employees"] == 2
    assert body["attendance_records_fetched"] == 40
    assert body["new_attendance_logs"] == 5
    assert body["placeholder_employees_created"] == 1
    assert device_sync.call_args.kwargs.get("full_resync") is True


def test_sync_device_unauthenticated(client: TestClient) -> None:
    response = client.post("/sync/device")
    assert response.status_code in {401, 403}
