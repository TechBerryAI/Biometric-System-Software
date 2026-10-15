"""FastAPI middleware injecting tenant context into requests."""

from __future__ import annotations

import threading
import time

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import SessionLocal
from app.core.tenant_context import TenantContext, resolve_tenant_context

# Tenants change rarely; caching avoids a database round trip on every API request.
_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, TenantContext]] = {}
_cache_lock = threading.Lock()


def reset_tenant_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_key(request: Request) -> str:
    header_tenant = request.headers.get("x-tenant-id") or ""
    return header_tenant if header_tenant.isdigit() else "default"


def _resolve(request: Request) -> TenantContext | None:
    key = _cache_key(request)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]

    db = SessionLocal()
    try:
        ctx = resolve_tenant_context(db, request=request)
        # Persist the default tenant if this request had to create it.
        db.commit()
    except Exception:  # noqa: BLE001 — close() below rolls back
        return None
    finally:
        db.close()
    with _cache_lock:
        _cache[key] = (now + _CACHE_TTL_SECONDS, ctx)
    return ctx


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant context for each request (public paths skipped)."""

    SKIP_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/auth/login", "/auth/refresh")

    async def dispatch(self, request: Request, call_next) -> Response:
        if any(request.url.path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return await call_next(request)

        # Database I/O is blocking; run it in the threadpool instead of stalling the event loop.
        request.state.tenant_context = await run_in_threadpool(_resolve, request)
        return await call_next(request)
