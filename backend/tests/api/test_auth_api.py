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


@pytest.mark.testid("BE-API-AUTH-011")
def test_forgot_password_unknown_email_is_rejected(client: TestClient, db_session) -> None:
    from app.domains.auth.models.password_reset_token import PasswordResetToken
    from app.domains.auth.models.user import User

    before = db_session.query(User).count()
    response = client.post("/auth/forgot-password", json={"email": "missing@example.com"})
    assert response.status_code == 404
    assert response.json()["detail"] == "No account found for this email."
    assert db_session.query(PasswordResetToken).count() == 0
    assert db_session.query(User).count() == before


@pytest.mark.testid("BE-API-AUTH-011")
def test_forgot_password_creates_token_and_sends_mail(
    client: TestClient, admin_user: User, db_session
) -> None:
    from unittest.mock import patch

    from app.domains.auth.models.password_reset_token import PasswordResetToken

    with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
        response = client.post("/auth/forgot-password", json={"email": admin_user.email})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert db_session.query(PasswordResetToken).count() == 1
    send_mail.assert_called_once()
    reset_url = send_mail.call_args.kwargs["reset_url"]
    assert "/reset-password?token=" in reset_url
    assert send_mail.call_args.kwargs["recipient"] == admin_user.email


@pytest.mark.testid("BE-API-AUTH-011")
def test_forgot_password_skips_env_operator(client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    from unittest.mock import patch

    from app.core.config import get_settings
    from app.domains.auth.models.password_reset_token import PasswordResetToken

    monkeypatch.setenv("AUTH_OPERATOR_EMAIL", "operator-env@example.com")
    monkeypatch.setenv("AUTH_OPERATOR_PASSWORD", "OperatorPass123!")
    get_settings.cache_clear()
    try:
        with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
            response = client.post("/auth/forgot-password", json={"email": "operator-env@example.com"})
        assert response.status_code == 404
        assert response.json()["detail"] == "No account found for this email."
        assert db_session.query(PasswordResetToken).count() == 0
        send_mail.assert_not_called()
    finally:
        get_settings.cache_clear()


@pytest.mark.testid("BE-API-AUTH-012")
def test_reset_password_success_and_old_password_fails(
    client: TestClient, admin_user: User, db_session
) -> None:
    from unittest.mock import patch

    with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
        forgot = client.post("/auth/forgot-password", json={"email": admin_user.email})
    assert forgot.status_code == 200
    raw_token = send_mail.call_args.kwargs["reset_url"].split("token=", 1)[1]

    reset = client.post(
        "/auth/reset-password",
        json={
            "token": raw_token,
            "new_password": "ResetPass123!",
            "confirm_password": "ResetPass123!",
        },
    )
    assert reset.status_code == 200
    assert reset.json()["status"] == "ok"

    old = client.post("/auth/login", json={"email": admin_user.email, "password": "Secret123!"})
    assert old.status_code == 401
    new = client.post("/auth/login", json={"email": admin_user.email, "password": "ResetPass123!"})
    assert new.status_code == 200


@pytest.mark.testid("BE-API-AUTH-012")
def test_reset_password_rejects_expired_and_used_tokens(
    client: TestClient, admin_user: User, db_session
) -> None:
    from datetime import datetime, timedelta
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    from app.domains.auth.models.password_reset_token import PasswordResetToken

    with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
        client.post("/auth/forgot-password", json={"email": admin_user.email})
    raw_token = send_mail.call_args.kwargs["reset_url"].split("token=", 1)[1]

    first = client.post(
        "/auth/reset-password",
        json={
            "token": raw_token,
            "new_password": "ResetPass123!",
            "confirm_password": "ResetPass123!",
        },
    )
    assert first.status_code == 200
    reused = client.post(
        "/auth/reset-password",
        json={
            "token": raw_token,
            "new_password": "AnotherPass123!",
            "confirm_password": "AnotherPass123!",
        },
    )
    assert reused.status_code == 400
    assert reused.json()["detail"] == "Invalid or expired reset token"

    with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
        client.post("/auth/forgot-password", json={"email": admin_user.email})
    expired_token = send_mail.call_args.kwargs["reset_url"].split("token=", 1)[1]
    row = db_session.query(PasswordResetToken).order_by(PasswordResetToken.id.desc()).first()
    assert row is not None
    row.expires_at = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=1)
    db_session.commit()

    expired = client.post(
        "/auth/reset-password",
        json={
            "token": expired_token,
            "new_password": "FreshPass123!",
            "confirm_password": "FreshPass123!",
        },
    )
    assert expired.status_code == 400


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
