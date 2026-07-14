"""Distributed locks for attendance correction and sync coordination."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import date
from typing import Iterator

from redis import Redis

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_local_locks: dict[str, threading.Lock] = {}
_local_guard = threading.Lock()


def _employee_day_lock_key(employee_id: int, local_date: date, settings: Settings) -> str:
    return f"{settings.redis_namespace}:attendance:employee_day:{employee_id}:{local_date.isoformat()}"


def _acquire_local_lock(key: str, *, blocking_timeout: float) -> threading.Lock | None:
    with _local_guard:
        lock = _local_locks.setdefault(key, threading.Lock())
    acquired = lock.acquire(blocking=True, timeout=blocking_timeout)
    return lock if acquired else None


@contextmanager
def employee_day_lock(
    employee_id: int,
    local_date: date,
    settings: Settings | None = None,
    *,
    blocking_timeout: float | None = None,
) -> Iterator[None]:
    """Serialize correction, effective-punch rebuild, and session rebuild for one employee-day."""
    settings = settings or get_settings()
    wait_seconds = blocking_timeout if blocking_timeout is not None else max(settings.command_lock_blocking_seconds, 30)
    key = _employee_day_lock_key(employee_id, local_date, settings)
    client = None
    lock = None
    local_lock: threading.Lock | None = None
    try:
        try:
            client = Redis.from_url(str(settings.redis_url), socket_timeout=2, socket_connect_timeout=2)
            lock_timeout = settings.zk_device_timeout_seconds + settings.command_heartbeat_seconds + 30
            lock = client.lock(key, timeout=lock_timeout, blocking_timeout=wait_seconds)
            if not lock.acquire(blocking=True, blocking_timeout=wait_seconds):
                raise RuntimeError(
                    f"Employee-day lock busy (employee={employee_id} date={local_date.isoformat()}). Retry shortly."
                )
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis employee-day lock unavailable (%s); using in-process fallback", exc)
            local_lock = _acquire_local_lock(key, blocking_timeout=wait_seconds)
            if local_lock is None:
                raise RuntimeError(
                    f"Employee-day lock busy (employee={employee_id} date={local_date.isoformat()}). Retry shortly."
                ) from exc
        yield
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:  # noqa: BLE001
                pass
        if local_lock is not None:
            try:
                local_lock.release()
            except Exception:  # noqa: BLE001
                pass
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
