"""API tests for /auth* endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domains.auth.models.user import User


@pytest.mark.testid("BE-API-AUTH-001")
def test_bootstrap_admin(client: TestClient) -> None:
    response = client.post("/auth/bootstrap-admin")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "bootstrap@example.com"
    assert body["role"] == "SUPER_ADMIN"
    assert body["active"] is True


@pytest.mark.testid("BE-API-AUTH-002")
def test_login_success(client: TestClient, admin_user: User) -> None:
    response = client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["role"] == "SUPER_ADMIN"


@pytest.mark.testid("BE-API-AUTH-003")
def test_refresh(client: TestClient, admin_user: User) -> None:
    from datetime import datetime
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    login = client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!"},
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    # SQLite drops tzinfo on DateTime(timezone=True); keep comparison types aligned.
    def _naive_utc() -> datetime:
        return datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)

    with patch("app.domains.auth.services.auth_service._utcnow", _naive_utc):
        response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["refresh_token"] != refresh_token


@pytest.mark.testid("BE-API-AUTH-004")
def test_logout(client: TestClient, admin_user: User) -> None:
    login = client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = client.post(
        "/auth/logout",
        headers=headers,
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.testid("BE-API-AUTH-005")
def test_me(client: TestClient, admin_user: User, admin_headers: dict[str, str]) -> None:
    response = client.get("/auth/me", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == admin_user.email
    assert body["role"] == admin_user.role
    assert "capabilities" in body


@pytest.mark.testid("BE-API-AUTH-006")
def test_update_me(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put("/auth/me", headers=admin_headers, json={"full_name": "Updated Admin"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Admin"


@pytest.mark.testid("BE-API-AUTH-007")
def test_change_password(client: TestClient, admin_user: User, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/auth/me/password",
        headers=admin_headers,
        json={
            "current_password": "Secret123!",
            "new_password": "NewSecret123!",
            "confirm_password": "NewSecret123!",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]

    # Old password should fail; new password should succeed.
    old = client.post("/auth/login", json={"email": admin_user.email, "password": "Secret123!"})
    assert old.status_code == 401
    new = client.post("/auth/login", json={"email": admin_user.email, "password": "NewSecret123!"})
    assert new.status_code == 200


@pytest.mark.testid("BE-API-AUTH-008")
def test_create_user_as_admin(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/auth/users",
        headers=admin_headers,
        json={
            "email": "new.hr@example.com",
            "full_name": "New HR",
            "password": "HrPass123!",
            "role": "HR_ADMIN",
            "active": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new.hr@example.com"
    assert body["role"] == "HR_ADMIN"


@pytest.mark.testid("BE-API-AUTH-009")
def test_login_wrong_password(client: TestClient, admin_user: User) -> None:
    response = client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "WrongPass999!"},
    )
    assert response.status_code == 401


@pytest.mark.testid("BE-API-AUTH-010")
def test_login_mfa_decrypt_failure_returns_401(
    client: TestClient,
    admin_user: User,
    db_session,
) -> None:
    admin_user.mfa_enabled = True
    admin_user.mfa_secret_encrypted = "not-valid-ciphertext"
    db_session.commit()

    response = client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!", "mfa_code": "123456"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid MFA code"
