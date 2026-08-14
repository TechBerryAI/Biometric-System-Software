"""Redis cache helpers for dashboard KPIs and general key/value JSON."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace

logger = logging.getLogger(__name__)


class RedisCache:
    """Tenant-aware JSON cache with safe no-op when Redis is unavailable."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._ttl = self._settings.dashboard_cache_ttl_seconds
        self._namespace = self._settings.redis_namespace
        self._client: redis.Redis | None = None
        try:
            self._client = redis.Redis.from_url(str(self._settings.redis_url), decode_responses=True)
            self._client.ping()
        except Exception as exc:  # noqa: BLE001
            self._client = None
            logger.debug("Redis cache unavailable: %s", exc)

    def _key(self, key: str, *, tenant_id: int | None = None) -> str:
        scoped = f"t{tenant_id}:{key}" if tenant_id is not None else key
        return with_namespace(self._namespace, scoped)

    def get_json(self, key: str, *, tenant_id: int | None = None) -> dict[str, Any] | None:
        if self._client is None:
            return None
        namespaced = self._key(key, tenant_id=tenant_id)
        try:
            raw = self._client.get(namespaced)
            if raw is None:
                return None
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.get_failed key=%s error=%s", namespaced, exc)
            return None

    def set_json(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        tenant_id: int | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        if self._client is None:
            return
        namespaced = self._key(key, tenant_id=tenant_id)
        try:
            self._client.setex(
                namespaced,
                ttl_seconds or self._ttl,
                json.dumps(payload, separators=(",", ":"), default=str),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.set_failed key=%s error=%s", namespaced, exc)

    def delete(self, key: str, *, tenant_id: int | None = None) -> None:
        if self._client is None:
            return
        namespaced = self._key(key, tenant_id=tenant_id)
        try:
            self._client.delete(namespaced)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.delete_failed key=%s error=%s", namespaced, exc)

    def delete_prefix(self, prefix: str, *, tenant_id: int | None = None) -> int:
        if self._client is None:
            return 0
        namespaced_prefix = self._key(prefix, tenant_id=tenant_id)
        try:
            keys = list(self._client.scan_iter(match=f"{namespaced_prefix}*"))
            if keys:
                return int(self._client.delete(*keys))
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.invalidate_failed prefix=%s error=%s", namespaced_prefix, exc)
            return 0


_cache: RedisCache | None = None


def get_cache(settings: Settings | None = None) -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache(settings=settings)
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None
