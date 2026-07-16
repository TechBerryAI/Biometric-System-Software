"""FastAPI middleware injecting tenant context into requests."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import SessionLocal
from app.core.tenant_context import resolve_tenant_context


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant context for each request (public paths skipped)."""

    SKIP_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/auth/login", "/auth/refresh")

    async def dispatch(self, request: Request, call_next) -> Response:
        if any(request.url.path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return await call_next(request)

        db = SessionLocal()
        try:
            ctx = resolve_tenant_context(db, request=request)
            request.state.tenant_context = ctx
        except Exception:  # noqa: BLE001
            request.state.tenant_context = None
        finally:
            db.close()

        return await call_next(request)
