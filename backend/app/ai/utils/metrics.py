"""Lightweight in-process AI metrics counters."""

from __future__ import annotations

import threading
from collections import defaultdict

_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = defaultdict(int)


def incr(metric: str, value: int = 1) -> None:
    with _LOCK:
        _COUNTERS[metric] += value


def snapshot() -> dict[str, int]:
    with _LOCK:
        return dict(_COUNTERS)

