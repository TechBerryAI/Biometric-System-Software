"""Double-submit cookie CSRF protection."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.core.config import get_settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_EXEMPT_PREFIXES = (
    "/health",
    "/devices/gateway/push",
    "/auth/forgot-password",
    "/auth/reset-password",
)

CsrfHandler = Callable[[Request], Awaitable[Response]]


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str, *, secure: bool = False) -> None:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


def _is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES)


async def csrf_middleware(request: Request, call_next: CsrfHandler) -> Response:
    settings = get_settings()
    if not settings.csrf_enabled:
        return await call_next(request)
    if request.method in SAFE_METHODS or _is_exempt(request.url.path):
        return await call_next(request)

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token or cookie_token != header_token:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "CSRF validation failed"},
        )
    return await call_next(request)
