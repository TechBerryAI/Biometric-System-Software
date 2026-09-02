"""API tests for env-backed GOD-mode operator authentication."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.operator_access import OperatorRefreshTokenStore
from app.core.security import hash_refresh_token
from app.domains.auth.models.user import User


class _InMemoryOperatorRefreshStore(OperatorRefreshTokenStore):
    _shared: dict[str, str] = {}

    def __init__(self, settings=None) -> None:
        super().__init__(settings)
        self._redis = None

    def store(self, *, token_hash: str, family_id: str, expires_at: datetime) -> bool:
        payload = json.dumps(
            {
                "family_id": family_id,
                "expires_at": expires_at.astimezone(ZoneInfo("UTC")).isoformat(),
                "revoked": False,
            }
        )
        self._shared[token_hash] = payload
        return True

    def load(self, token_hash: str) -> dict[str, str | bool] | None:
        raw = self._shared.get(token_hash)
        if raw is None:
            return None
        return json.loads(raw)

    def delete(self, token_hash: str) -> None:
        self._shared.pop(token_hash, None)

    def revoke_family(self, family_id: str) -> None:
        for key, raw in list(self._shared.items()):
            data = json.loads(raw)
            if data.get("family_id") == family_id:
                self._shared.pop(key, None)


@pytest.fixture()
def env_operator_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_OPERATOR_EMAIL", "operator-env@example.com")
    monkeypatch.setenv("AUTH_OPERATOR_PASSWORD", "OperatorPass123!")
    monkeypatch.setenv("AUTH_OPERATOR_UUID", "usr_operator_test099")
    get_settings.cache_clear()
    _InMemoryOperatorRefreshStore._shared.clear()
    yield
    get_settings.cache_clear()
    _InMemoryOperatorRefreshStore._shared.clear()


@pytest.fixture()
def env_operator_client(client: TestClient, env_operator_settings: None):
    with patch(
        "app.core.operator_access.OperatorRefreshTokenStore",
        _InMemoryOperatorRefreshStore,
    ):
        yield client


@pytest.mark.testid("BE-API-ENV-OP-001")
def test_env_operator_login_without_db_row(env_operator_client: TestClient, db_session) -> None:
    count = db_session.execute(
        select(User).where(User.email == "operator-env@example.com")
    ).scalar_one_or_none()
    assert count is None

    response = env_operator_client.post(
        "/auth/login",
        json={"email": "operator-env@example.com", "password": "OperatorPass123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["role"] == "SUPER_ADMIN"


@pytest.mark.testid("BE-API-ENV-OP-002")
def test_env_operator_me_capabilities(env_operator_client: TestClient) -> None:
    login = env_operator_client.post(
        "/auth/login",
        json={"email": "operator-env@example.com", "password": "OperatorPass123!"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = env_operator_client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "operator-env@example.com"
    assert body["capabilities"]["attendance_adjust"] is True
    assert body["capabilities"]["forensic_audit"] is True


@pytest.mark.testid("BE-API-ENV-OP-003")
def test_env_operator_refresh(env_operator_client: TestClient) -> None:
    login = env_operator_client.post(
        "/auth/login",
        json={"email": "operator-env@example.com", "password": "OperatorPass123!"},
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    def _naive_utc() -> datetime:
        return datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)

    with patch("app.domains.auth.services.auth_service._utcnow", _naive_utc):
        response = env_operator_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["refresh_token"] != refresh_token


@pytest.mark.testid("BE-API-ENV-OP-004")
def test_env_operator_blocks_profile_update(env_operator_client: TestClient) -> None:
    login = env_operator_client.post(
        "/auth/login",
        json={"email": "operator-env@example.com", "password": "OperatorPass123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = env_operator_client.put("/auth/me", headers=headers, json={"full_name": "Nope"})
    assert response.status_code == 403


@pytest.mark.testid("BE-API-ENV-OP-005")
def test_env_operator_blocks_password_change(env_operator_client: TestClient) -> None:
    login = env_operator_client.post(
        "/auth/login",
        json={"email": "operator-env@example.com", "password": "OperatorPass123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = env_operator_client.post(
        "/auth/me/password",
        headers=headers,
        json={
            "current_password": "OperatorPass123!",
            "new_password": "NewPass123!",
            "confirm_password": "NewPass123!",
        },
    )
    assert response.status_code == 403


@pytest.mark.testid("BE-API-ENV-OP-006")
def test_create_user_rejects_operator_email(
    env_operator_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = env_operator_client.post(
        "/auth/users",
        headers=admin_headers,
        json={
            "email": "operator-env@example.com",
            "full_name": "Sneaky",
            "password": "HrPass123!",
            "role": "HR_ADMIN",
            "active": True,
        },
    )
    assert response.status_code == 403


@pytest.mark.testid("BE-API-ENV-OP-007")
def test_db_user_still_authenticates(
    env_operator_client: TestClient,
    admin_user: User,
) -> None:
    response = env_operator_client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "SUPER_ADMIN"


@pytest.mark.testid("BE-UNIT-ENV-OP-001")
def test_operator_refresh_store_roundtrip() -> None:
    store = _InMemoryOperatorRefreshStore()
    expires = datetime.now(ZoneInfo("UTC")) + timedelta(days=7)
    token = "sample-refresh-token"
    token_hash = hash_refresh_token(token)
    assert store.store(token_hash=token_hash, family_id="fam-1", expires_at=expires) is True
    loaded = store.load(token_hash)
    assert loaded is not None
    assert loaded["family_id"] == "fam-1"
    store.delete(token_hash)
    assert store.load(token_hash) is None
