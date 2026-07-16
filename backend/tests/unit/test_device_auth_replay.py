"""Verify push device auth replay protection uses redis namespace correctly."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domains.devices.gateway.device_auth import DeviceAuthService


@pytest.mark.testid("BE-UNIT-REPLAY-001")
def test_nonce_key_uses_string_namespace() -> None:
    settings = MagicMock(redis_namespace="biometric", redis_url="redis://localhost:6379/15")
    svc = DeviceAuthService(settings=settings)
    key = svc._nonce_key("gate-1", "abc")
    assert key == "biometric:device:nonce:gate-1:abc"


@pytest.mark.testid("BE-UNIT-REPLAY-002")
def test_is_replay_sets_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock(redis_namespace="biometric", redis_url="redis://localhost:6379/15")
    svc = DeviceAuthService(settings=settings)
    fake = MagicMock()
    fake.get.return_value = None
    monkeypatch.setattr(svc, "_redis", lambda: fake)
    assert svc.is_replay("gate-1", "n1") is False
    fake.setex.assert_called_once()
    fake.get.return_value = "1"
    assert svc.is_replay("gate-1", "n1") is True
