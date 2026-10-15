"""API tests for /health* endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.testid("BE-API-HLTH-001")
def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "service" in body


@pytest.mark.testid("BE-API-HLTH-002")
def test_health_db(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/health/db", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.testid("BE-API-HLTH-003")
def test_health_redis(client: TestClient, admin_headers: dict[str, str]) -> None:
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    with patch("app.domains.ops.health.Redis") as redis_cls:
        redis_cls.from_url.return_value = mock_client
        response = client.get("/health/redis", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_client.ping.assert_called_once()


@pytest.mark.testid("BE-API-HLTH-004")
def test_health_devices(client: TestClient, admin_headers: dict[str, str]) -> None:
    with (
        patch("app.domains.ops.health.device_service_for") as svc_for,
        patch("app.domains.ops.health.update_device_health") as _update,
        patch("app.domains.ops.health.ensure_default_device") as ensure,
    ):
        instance = MagicMock()
        instance.check_connection.return_value = (True, "ok")
        instance.detect_firmware_fingerprint.return_value = {
            "firmware_version": "1.0.0",
            "serial_number": "SN-TEST",
            "platform": "test",
        }
        instance.connection.ip_address = "192.168.1.85"
        instance.connection.port = 4370
        svc_for.return_value = instance
        registered = MagicMock()
        registered.name = "main-entrance"
        registered.mode = "NORMAL"
        registered.ip_address = "192.168.1.85"
        ensure.return_value = registered
        response = client.get("/health/devices", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["firmware_version"] == "1.0.0"
    svc_for.assert_called_once()
    called_kwargs = svc_for.call_args.kwargs
    assert called_kwargs.get("device_name") == "main-entrance"


@pytest.mark.testid("BE-API-HLTH-005")
def test_health_ai(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/health/ai", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}


@pytest.mark.testid("BE-API-HLTH-006")
def test_health_queue(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/health/queue", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "queue_depth" in body
    assert "stale_commands" in body
    assert "dead_letter_commands" in body


@pytest.mark.testid("BE-API-HLTH-007")
def test_health_reconciliation(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/health/reconciliation", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "pending_jobs" in body
    assert "completed_jobs" in body


@pytest.mark.testid("BE-API-HLTH-008")
def test_health_redis_unauthorized(client: TestClient) -> None:
    response = client.get("/health/redis")
    assert response.status_code in {401, 403}


@pytest.mark.testid("BE-API-HLTH-010")
def test_database_outage_returns_retryable_503(client: TestClient, admin_headers: dict[str, str]) -> None:
    from sqlalchemy.exc import OperationalError

    from app.core.database import get_db
    from app.main import app

    def _db_down():  # type: ignore[no-untyped-def]
        raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _db_down
    response = client.get("/health/db", headers=admin_headers)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert "temporarily unavailable" in response.json()["detail"]
