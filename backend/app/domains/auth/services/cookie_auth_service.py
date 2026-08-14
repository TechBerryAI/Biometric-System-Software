"""HttpOnly cookie helpers for dual-mode Bearer + cookie authentication."""

from __future__ import annotations

from datetime import datetime

from fastapi import Request, Response

from app.core.config import Settings, get_settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _cookie_secure(settings: Settings) -> bool:
    return settings.environment == "production"


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    if not settings.auth_cookie_enabled:
        return

    secure = _cookie_secure(settings)
    max_age_access = settings.access_token_expire_minutes * 60
    max_age_refresh = settings.refresh_token_expire_days * 86400
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age_access,
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age_refresh,
    )


def clear_auth_cookies(response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.auth_cookie_enabled:
        return
    response.delete_cookie(key=ACCESS_COOKIE, path="/")
    response.delete_cookie(key=REFRESH_COOKIE, path="/")


def read_access_token_from_request(request: Request) -> str | None:
    return request.cookies.get(ACCESS_COOKIE)


def read_refresh_token_from_request(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


def resolve_refresh_token(request: Request, body_token: str | None = None) -> str | None:
    if body_token:
        return body_token
    return read_refresh_token_from_request(request)


def resolve_access_token(request: Request, bearer_token: str | None = None) -> str | None:
    if bearer_token:
        return bearer_token
    return read_access_token_from_request(request)


def should_omit_token_body(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return settings.auth_cookie_enabled and settings.auth_cookie_only
