"""Redis singleton locks so beat-fired Celery tasks do not overlap."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from app.core.config import get_settings
from app.core.redis_lock import get_redlock

logger = logging.getLogger(__name__)

# Skip reason returned when another worker already holds the task lock.
SKIPPED_ALREADY_RUNNING: dict[str, object] = {"skipped": True, "reason": "already_running"}


@contextmanager
def task_singleton(name: str, *, ttl_ms: int) -> Iterator[bool]:
    """Try to acquire a non-blocking Redis lock for a Celery task.

    Yields ``True`` when the caller should run the task, ``False`` when another
    instance already holds the lock. If Redis is unavailable, yields ``True``
    (fail open) so scheduled work still progresses.
    """
    settings = get_settings()
    redlock = get_redlock(settings)
    if not redlock._clients:  # noqa: SLF001 — empty client list means Redis unavailable
        logger.warning("Celery task singleton unavailable name=%s; running without lock", name)
        yield True
        return

    handle = redlock.acquire(f"celery:task:{name}", ttl_ms=ttl_ms, blocking_timeout=0)
    if handle is None:
        logger.info("Celery task singleton busy name=%s", name)
        yield False
        return

    try:
        yield True
    finally:
        redlock.release(handle)
