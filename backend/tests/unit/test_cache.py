"""Unit tests for Redis cache helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.cache import RedisCache, reset_cache


@pytest.mark.testid("BE-UNIT-CACHE-001")
def test_cache_noop_without_redis() -> None:
    reset_cache()
    cache = RedisCache.__new__(RedisCache)
    cache._settings = MagicMock(redis_namespace="biometric", dashboard_cache_ttl_seconds=60, redis_url="redis://x")
    cache._ttl = 60
    cache._namespace = "biometric"
    cache._client = None
    assert cache.get_json("k") is None
    cache.set_json("k", {"a": 1})
    assert cache.delete("k") is None
    assert cache.delete_prefix("k") == 0


@pytest.mark.testid("BE-UNIT-CACHE-002")
def test_cache_get_set_with_fake_redis() -> None:
    reset_cache()
    cache = RedisCache.__new__(RedisCache)
    cache._settings = MagicMock(redis_namespace="biometric", dashboard_cache_ttl_seconds=60)
    cache._ttl = 60
    cache._namespace = "biometric"
    fake = MagicMock()
    fake.get.return_value = '{"x": 1}'
    cache._client = fake
    assert cache.get_json("kpi", tenant_id=1) == {"x": 1}
    cache.set_json("kpi", {"y": 2}, tenant_id=1)
    fake.setex.assert_called_once()
    reset_cache()
