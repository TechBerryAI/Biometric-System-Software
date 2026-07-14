"""Unit tests for AI response cache."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ai.cache.redis_cache import AIResponseCache
from app.core.config import get_settings


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    def scan_iter(self, match: str = "*"):
        prefix = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                n += 1
        return n


@pytest.mark.testid("BE-UNIT-AI-CACHE-001")
def test_ai_response_cache_get_set_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr("app.ai.cache.redis_cache.redis.Redis.from_url", lambda *a, **k: fake)

    cache = AIResponseCache(get_settings())
    assert cache.get_json("unit:missing") is None

    cache.set_json("unit:key", {"hello": "world"}, ttl_seconds=60)
    assert cache.get_json("unit:key") == {"hello": "world"}

    cache.delete_prefix("unit:")
    assert cache.get_json("unit:key") is None


@pytest.mark.testid("BE-UNIT-AI-CACHE-001")
def test_ai_response_cache_noop_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a, **_k):
        raise OSError("no redis")

    monkeypatch.setattr("app.ai.cache.redis_cache.redis.Redis.from_url", _boom)
    cache = AIResponseCache(get_settings())
    cache.set_json("k", {"x": 1})
    assert cache.get_json("k") is None
