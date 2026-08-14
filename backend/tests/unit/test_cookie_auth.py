"""Unit tests for cookie-based authentication helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.responses import Response

from app.domains.auth.services.cookie_auth_service import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    read_access_token_from_request,
    read_refresh_token_from_request,
    resolve_refresh_token,
    set_auth_cookies,
    should_omit_token_body,
)


class _FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.cookies = cookies or {}


@pytest.mark.testid("BE-UNIT-COOKIE-001")
def test_set_auth_cookies_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_COOKIE_ENABLED", "true")
    monkeypatch.setenv("DEBUG", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    response = Response()
    set_auth_cookies(response, access_token="access-1", refresh_token="refresh-1")
    headers = response.headers.getlist("set-cookie")
    assert any(ACCESS_COOKIE in header and "access-1" in header for header in headers)
    assert any(REFRESH_COOKIE in header and "refresh-1" in header for header in headers)


@pytest.mark.testid("BE-UNIT-COOKIE-002")
def test_set_auth_cookies_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_COOKIE_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    response = Response()
    set_auth_cookies(response, access_token="access-1", refresh_token="refresh-1")
    assert response.headers.get("set-cookie") is None


@pytest.mark.testid("BE-UNIT-COOKIE-003")
def test_resolve_refresh_token_prefers_body() -> None:
    request = _FakeRequest({REFRESH_COOKIE: "cookie-token"})
    assert resolve_refresh_token(request, "body-token") == "body-token"


@pytest.mark.testid("BE-UNIT-COOKIE-004")
def test_read_tokens_from_request_cookies() -> None:
    request = _FakeRequest({ACCESS_COOKIE: "access-token", REFRESH_COOKIE: "refresh-token"})
    assert read_access_token_from_request(request) == "access-token"
    assert read_refresh_token_from_request(request) == "refresh-token"
    assert resolve_refresh_token(request) == "refresh-token"


@pytest.mark.testid("BE-UNIT-COOKIE-005")
def test_should_omit_token_body_when_cookie_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_COOKIE_ENABLED", "true")
    monkeypatch.setenv("AUTH_COOKIE_ONLY", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert should_omit_token_body() is True


@pytest.mark.testid("BE-UNIT-COOKIE-006")
def test_clear_auth_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_COOKIE_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    response = Response()
    clear_auth_cookies(response)
    headers = response.headers.getlist("set-cookie")
    assert any(ACCESS_COOKIE in header for header in headers)
    assert any(REFRESH_COOKIE in header for header in headers)
