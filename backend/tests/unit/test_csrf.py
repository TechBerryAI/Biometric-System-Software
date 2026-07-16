"""Unit tests for CSRF double-submit cookie protection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import Response

from app.core.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    clear_csrf_cookie,
    csrf_middleware,
    generate_csrf_token,
    set_csrf_cookie,
)


@pytest.mark.testid("BE-UNIT-CSRF-001")
def test_generate_csrf_token_is_unique() -> None:
    assert generate_csrf_token() != generate_csrf_token()


@pytest.mark.testid("BE-UNIT-CSRF-002")
def test_set_and_clear_csrf_cookie() -> None:
    response = Response()
    token = generate_csrf_token()
    set_csrf_cookie(response, token, secure=False)
    header = response.headers.get("set-cookie", "")
    assert CSRF_COOKIE_NAME in header
    assert token in header

    clear_csrf_cookie(response)
    cleared = response.headers.getlist("set-cookie")
    assert any(CSRF_COOKIE_NAME in value and '=""' in value.replace(" ", "") for value in cleared)


@pytest.mark.testid("BE-UNIT-CSRF-003")
@pytest.mark.asyncio
async def test_csrf_middleware_rejects_missing_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CSRF_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    request = MagicMock()
    request.method = "POST"
    request.url.path = "/auth/logout"
    request.cookies = {CSRF_COOKIE_NAME: "abc123"}
    request.headers = {}

    handler = AsyncMock(return_value=Response(status_code=200))
    response = await csrf_middleware(request, handler)
    assert response.status_code == 403
    handler.assert_not_called()


@pytest.mark.testid("BE-UNIT-CSRF-004")
@pytest.mark.asyncio
async def test_csrf_middleware_allows_matching_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CSRF_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()

    token = "abc123"
    request = MagicMock()
    request.method = "POST"
    request.url.path = "/auth/logout"
    request.cookies = {CSRF_COOKIE_NAME: token}
    request.headers = {CSRF_HEADER_NAME: token}

    handler = AsyncMock(return_value=Response(status_code=200))
    response = await csrf_middleware(request, handler)
    assert response.status_code == 200
    handler.assert_called_once()
