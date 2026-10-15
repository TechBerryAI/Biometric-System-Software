"""Unit tests for tenant context caching in the request middleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core import tenant_middleware
from app.core.tenant_context import TenantContext


def _request(tenant_header: str | None = None) -> MagicMock:
    request = MagicMock()
    request.headers = {"x-tenant-id": tenant_header} if tenant_header else {}
    return request


@pytest.mark.testid("BE-UNIT-TENANT-001")
def test_tenant_context_is_cached_between_requests() -> None:
    tenant_middleware.reset_tenant_cache()
    ctx = TenantContext(tenant_id=1, tenant_uuid="ten_1", tenant_slug="default", deployment_mode="saas")
    with (
        patch.object(tenant_middleware, "SessionLocal", return_value=MagicMock()),
        patch.object(tenant_middleware, "resolve_tenant_context", return_value=ctx) as resolve,
    ):
        assert tenant_middleware._resolve(_request()) is ctx
        assert tenant_middleware._resolve(_request()) is ctx
        assert resolve.call_count == 1
        # A different tenant header is a different cache entry.
        tenant_middleware._resolve(_request("2"))
        assert resolve.call_count == 2
    tenant_middleware.reset_tenant_cache()


@pytest.mark.testid("BE-UNIT-TENANT-002")
def test_tenant_resolution_failure_is_not_cached() -> None:
    tenant_middleware.reset_tenant_cache()
    with (
        patch.object(tenant_middleware, "SessionLocal", return_value=MagicMock()),
        patch.object(tenant_middleware, "resolve_tenant_context", side_effect=RuntimeError("db down")) as resolve,
    ):
        assert tenant_middleware._resolve(_request()) is None
        assert tenant_middleware._resolve(_request()) is None
        assert resolve.call_count == 2
    tenant_middleware.reset_tenant_cache()
