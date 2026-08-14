"""Shared circuit breaker (tenacity-compatible retry wrapper)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when the circuit is open and calls are short-circuited."""


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    """Simple failure-threshold circuit breaker with half-open reset window."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_seconds: float = 60,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.name = name
        self._state = CircuitState()
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self._state.opened_at is None:
                return True
            if time.time() - self._state.opened_at >= self.reset_seconds:
                self._state.opened_at = None
                self._state.failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state.failures = 0
            self._state.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._state.failures += 1
            if self._state.failures >= self.failure_threshold:
                self._state.opened_at = time.time()
                logger.warning(
                    "circuit_open name=%s failures=%s reset_seconds=%s",
                    self.name,
                    self._state.failures,
                    self.reset_seconds,
                )

    def opened_until(self) -> datetime | None:
        with self._lock:
            if self._state.opened_at is None:
                return None
            return datetime.fromtimestamp(
                self._state.opened_at + self.reset_seconds,
                tz=timezone.utc,
            )

    def call(self, fn: Callable[[], T], *, retry_attempts: int = 1) -> T:
        if not self.can_execute():
            raise CircuitOpenError(f"Circuit '{self.name}' is open until {self.opened_until()}")

        @retry(
            reraise=True,
            stop=stop_after_attempt(max(1, retry_attempts)),
            wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
            retry=retry_if_exception_type(Exception),
        )
        def _inner() -> T:
            return fn()

        try:
            result = _inner()
            self.record_success()
            return result
        except RetryError as exc:
            self.record_failure()
            raise exc.last_attempt.exception() from exc  # type: ignore[misc]
        except Exception:
            self.record_failure()
            raise
