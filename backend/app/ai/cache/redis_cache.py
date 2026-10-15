"""Redis cache with safe no-op fallback when unavailable."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.ai.utils.metrics import incr
from app.ai.utils.telemetry import log_ai_event
from app.core.config import Settings
from app.core.redis_client import redis_client_options
from app.core.redis_keys import with_namespace

log = logging.getLogger(__name__)


class AIResponseCache:
    def __init__(self, settings: Settings) -> None:
        self._ttl = settings.ai_cache_ttl
        self._namespace = settings.redis_namespace
        self._client: redis.Redis[str] | None = None
        try:
            self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True, **redis_client_options())
            self._client.ping()
            log_ai_event(log, "cache_ready", backend="redis")
        except Exception as exc:  # noqa: BLE001
            self._client = None
            log.warning("ai.cache.unavailable error=%s", exc)

    def get_json(self, key: str) -> dict[str, Any] | None:
        if self._client is None:
            return None
        namespaced_key = with_namespace(self._namespace, key)
        try:
            raw = self._client.get(namespaced_key)
            if raw is None:
                incr("ai_cache_miss")
                log_ai_event(log, "cache_miss", key=namespaced_key)
                return None
            incr("ai_cache_hit")
            log_ai_event(log, "cache_hit", key=namespaced_key)
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("ai.cache.get_failed key=%s error=%s", namespaced_key, exc)
            return None

    def set_json(self, key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> None:
        if self._client is None:
            return
        namespaced_key = with_namespace(self._namespace, key)
        try:
            self._client.setex(namespaced_key, ttl_seconds or self._ttl, json.dumps(payload, separators=(",", ":")))
            incr("ai_cache_write")
            log_ai_event(log, "cache_write", key=namespaced_key, ttl=ttl_seconds or self._ttl)
        except Exception as exc:  # noqa: BLE001
            log.warning("ai.cache.set_failed key=%s error=%s", namespaced_key, exc)

    def delete_prefix(self, prefix: str) -> None:
        if self._client is None:
            return
        namespaced_prefix = with_namespace(self._namespace, prefix)
        try:
            keys = list(self._client.scan_iter(match=f"{namespaced_prefix}*"))
            if keys:
                self._client.delete(*keys)
                log_ai_event(log, "cache_invalidate", prefix=namespaced_prefix, count=len(keys))
        except Exception as exc:  # noqa: BLE001
            log.warning("ai.cache.invalidate_failed prefix=%s error=%s", namespaced_prefix, exc)

