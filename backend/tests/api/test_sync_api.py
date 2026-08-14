"""API tests for /sync* endpoints."""

from __future__ import annotations

import errno
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from tests.factories import make_device


@contextmanager
def _noop_lock(*_args, **_kwargs):
    yield


@pytest.mark.testid("BE-API-SYNC-001")
def test_sync_device_success(client: TestClient, admin_headers: dict[str, str]) -> None:
    cache = MagicMock()
    sync_result = MagicMock(
        fetched=40,
        inserted=5,
        placeholders=1,
        skipped_reason=None,
        skipped_corrected_punches=2,
        punches_missing_after_insert=0,
    )
    with (
        patch("app.domains.devices.router.wait_for_correction_commands_clear", return_value=True),
        patch("app.domains.devices.router.device_session_lock", side_effect=_noop_lock),
        patch("app.domains.devices.router.run_user_sync", return_value=(12, 2)),
        patch("app.domains.devices.router.run_device_sync_detailed", return_value=sync_result) as device_sync,
        patch("app.domains.devices.router.update_device_health"),
        patch("app.domains.devices.router.get_or_create_sync_state", return_value=MagicMock()),
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
    assert body["skipped_corrected_punches"] == 2
    assert body["punches_missing_after_insert"] == 0
    assert device_sync.call_args.kwargs.get("full_resync") is True


@pytest.mark.testid("BE-API-SYNC-002")
def test_sync_device_error_reports_saved_ip_not_env(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    settings = get_settings()
    db_session.add(
        make_device(name=settings.zk_device_id, ip_address="192.168.1.85", port=4370, connectivity_mode="both")
    )
    db_session.commit()
    with (
        patch("app.domains.devices.router.wait_for_correction_commands_clear", return_value=True),
        patch("app.domains.devices.router.device_session_lock", side_effect=_noop_lock),
        patch("app.domains.devices.router.run_user_sync", return_value=(0, 0)),
        patch(
            "app.domains.devices.router.run_device_sync_detailed",
            side_effect=OSError(errno.EPIPE, "Broken pipe"),
        ),
        patch("app.domains.devices.router.update_device_health"),
    ):
        response = client.post("/sync/device", headers=admin_headers)
    assert response.status_code == 502
    detail = str(response.json()["detail"])
    assert "192.168.1.85:4370" in detail
    if settings.zk_device_ip != "192.168.1.85":
        assert settings.zk_device_ip not in detail


def test_sync_device_unauthenticated(client: TestClient) -> None:
    response = client.post("/sync/device")
    assert response.status_code in {401, 403}
