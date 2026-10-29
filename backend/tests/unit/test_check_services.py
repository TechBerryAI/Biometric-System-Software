"""Unit tests for the startup preflight diagnostics (backend/scripts/check_services.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_services.py"
_spec = importlib.util.spec_from_file_location("check_services", _SCRIPT)
assert _spec and _spec.loader
check_services = importlib.util.module_from_spec(_spec)
sys.modules["check_services"] = check_services  # dataclasses resolve their module by name
_spec.loader.exec_module(check_services)


class _Settings:
    database_url = "postgresql+psycopg://app:secret@db.example:6567/biometric_db"
    db_connect_timeout_seconds = 5
    db_application_name = "test"


@pytest.fixture()
def reachable_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_services, "_tcp_probe", lambda *a, **k: None)


@pytest.mark.testid("BE-UNIT-PREFLIGHT-001")
def test_bad_password_fails_fast_with_hint(monkeypatch: pytest.MonkeyPatch, reachable_port: None) -> None:
    def _connect(*_a: object, **_k: object) -> None:
        raise RuntimeError('connection failed: FATAL:  password authentication failed for user "app"')

    monkeypatch.setattr(check_services, "_pg_connect", _connect)
    result = check_services.check_database(_Settings())
    assert result.ok is False
    assert result.retryable is False
    assert any("DB_PASSWORD" in hint for hint in result.hints)
    assert "secret" not in result.summary


@pytest.mark.testid("BE-UNIT-PREFLIGHT-002")
def test_server_closed_connection_is_retried_with_host_checks(
    monkeypatch: pytest.MonkeyPatch, reachable_port: None
) -> None:
    def _connect(*_a: object, **_k: object) -> None:
        raise RuntimeError(
            'connection failed: connection to server at "db.example", port 6567 failed: '
            "server closed the connection unexpectedly"
        )

    monkeypatch.setattr(check_services, "_pg_connect", _connect)
    result = check_services.check_database(_Settings())
    assert result.ok is False
    assert result.retryable is True
    assert "handshake" in result.summary
    assert any("6567" in hint for hint in result.hints)


@pytest.mark.testid("BE-UNIT-PREFLIGHT-003")
def test_tls_only_failure_suggests_sslmode_disable(monkeypatch: pytest.MonkeyPatch, reachable_port: None) -> None:
    def _connect(*_a: object, **overrides: object) -> object:
        if overrides.get("sslmode") == "disable":
            return type("Conn", (), {"close": lambda self: None})()
        raise RuntimeError("connection failed: server closed the connection unexpectedly")

    monkeypatch.setattr(check_services, "_pg_connect", _connect)
    result = check_services.check_database(_Settings())
    assert result.ok is False
    assert result.retryable is False
    assert any("DB_SSLMODE=disable" in hint for hint in result.hints)


@pytest.mark.testid("BE-UNIT-PREFLIGHT-004")
def test_redis_url_password_is_masked() -> None:
    assert check_services._mask_url("redis://:hunter2@10.0.0.1:6379/0") == "redis://:***@10.0.0.1:6379/0"
    assert check_services._mask_url("redis://10.0.0.1:6379/0") == "redis://10.0.0.1:6379/0"


@pytest.mark.testid("BE-UNIT-PREFLIGHT-005")
def test_forever_mode_waits_until_database_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = iter(
        [
            check_services.CheckResult(ok=False, summary="PostgreSQL: server closed the connection"),
            check_services.CheckResult(ok=False, summary="PostgreSQL: server closed the connection"),
            check_services.CheckResult(ok=True, summary="PostgreSQL ok"),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(check_services, "check_database", lambda _settings: next(outcomes))
    monkeypatch.setattr(check_services.time, "sleep", sleeps.append)

    assert check_services.main(["--forever", "--skip-redis"]) == 0
    assert len(sleeps) == 2


@pytest.mark.testid("BE-UNIT-PREFLIGHT-006")
def test_forever_mode_still_exits_on_configuration_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = check_services.CheckResult(ok=False, retryable=False, summary="password authentication failed")
    monkeypatch.setattr(check_services, "check_database", lambda _settings: failure)
    monkeypatch.setattr(check_services.time, "sleep", lambda _s: pytest.fail("must not wait on a config error"))

    assert check_services.main(["--forever", "--skip-redis"]) == 1
