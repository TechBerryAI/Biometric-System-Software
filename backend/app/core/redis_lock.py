"""Distributed Redis locks (Redlock-style multi-node acquire)."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import redis

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace

logger = logging.getLogger(__name__)

# Release only if we still own the lock (Lua compare-and-del).
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
else
  return 0
end
"""


@dataclass
class LockHandle:
    key: str
    token: str
    clients: list[redis.Redis]
    acquired: bool


class Redlock:
    """Acquire a lock on a majority of Redis nodes (Redlock pattern).

    With a single REDIS_URL the majority is 1/1. Pass extra URLs via
    REDIS_LOCK_URLS (comma-separated) for true multi-node Redlock.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._clients = self._build_clients()
        self._quorum = max(1, (len(self._clients) // 2) + 1)

    def _build_clients(self) -> list[redis.Redis]:
        urls = [str(self._settings.redis_url)]
        extra = (self._settings.redis_lock_urls or "").strip()
        if extra:
            urls.extend(u.strip() for u in extra.split(",") if u.strip())
        clients: list[redis.Redis] = []
        for url in urls:
            try:
                client = redis.Redis.from_url(url, decode_responses=True)
                client.ping()
                clients.append(client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redlock node unavailable url=%s error=%s", url, exc)
        return clients

    def _namespaced(self, name: str) -> str:
        return with_namespace(self._settings.redis_namespace, f"lock:{name}")

    def acquire(
        self,
        name: str,
        *,
        ttl_ms: int = 30000,
        blocking_timeout: float = 0,
        retry_delay: float = 0.05,
    ) -> LockHandle | None:
        if not self._clients:
            return None
        key = self._namespaced(name)
        token = str(uuid.uuid4())
        deadline = time.monotonic() + max(0.0, blocking_timeout)
        while True:
            acquired_nodes: list[redis.Redis] = []
            start = time.monotonic()
            for client in self._clients:
                try:
                    ok = client.set(key, token, nx=True, px=ttl_ms)
                    if ok:
                        acquired_nodes.append(client)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Redlock set failed: %s", exc)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if len(acquired_nodes) >= self._quorum and elapsed_ms < ttl_ms:
                return LockHandle(key=key, token=token, clients=acquired_nodes, acquired=True)
            # Failed quorum — release partial acquires.
            for client in acquired_nodes:
                try:
                    client.eval(_RELEASE_SCRIPT, 1, key, token)
                except Exception:  # noqa: BLE001
                    pass
            if blocking_timeout <= 0 or time.monotonic() >= deadline:
                return None
            time.sleep(retry_delay)

    def release(self, handle: LockHandle | None) -> None:
        if handle is None or not handle.acquired:
            return
        for client in handle.clients:
            try:
                client.eval(_RELEASE_SCRIPT, 1, handle.key, handle.token)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redlock release failed: %s", exc)

    @contextmanager
    def lock(
        self,
        name: str,
        *,
        ttl_ms: int = 30000,
        blocking_timeout: float = 5,
    ) -> Iterator[LockHandle | None]:
        handle = self.acquire(name, ttl_ms=ttl_ms, blocking_timeout=blocking_timeout)
        try:
            yield handle
        finally:
            self.release(handle)


_redlock: Redlock | None = None


def get_redlock(settings: Settings | None = None) -> Redlock:
    global _redlock
    if _redlock is None:
        _redlock = Redlock(settings=settings)
    return _redlock


def reset_redlock() -> None:
    global _redlock
    _redlock = None
