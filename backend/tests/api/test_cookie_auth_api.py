"""API tests for cookie-based auth on /auth endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domains.auth.models.user import User
from app.domains.auth.services.cookie_auth_service import ACCESS_COOKIE, REFRESH_COOKIE


@pytest.fixture()
def cookie_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUTH_COOKIE_ENABLED", "true")
    monkeypatch.setenv("AUTH_COOKIE_ONLY", "false")
    monkeypatch.setenv("CSRF_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    return client


@pytest.mark.testid("BE-API-COOKIE-001")
def test_login_sets_auth_cookies(cookie_client: TestClient, admin_user: User) -> None:
    response = cookie_client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!"},
    )
    assert response.status_code == 200
    cookies = response.cookies
    assert ACCESS_COOKIE in cookies
    assert REFRESH_COOKIE in cookies
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.testid("BE-API-COOKIE-002")
def test_refresh_accepts_cookie_token(cookie_client: TestClient, admin_user: User) -> None:
    login = cookie_client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "Secret123!"},
    )
    assert login.status_code == 200

    response = cookie_client.post("/auth/refresh", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
