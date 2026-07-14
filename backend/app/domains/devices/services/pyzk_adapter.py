"""Defensive pyzk adapter with reconnect/timeouts containment."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from zk import ZK
from zk.exception import ZKError

from app.core.config import Settings

logger = logging.getLogger(__name__)
T = TypeVar("T")


class PyZKAdapter:
    """Isolate unstable pyzk behavior behind bounded retries and parsing guards."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _make_zk(self) -> ZK:
        return ZK(
            self._settings.zk_device_ip,
            port=self._settings.zk_device_port,
            timeout=self._settings.zk_device_timeout_seconds,
            password=self._settings.zk_device_password,
            force_udp=self._settings.zk_force_udp,
            ommit_ping=self._settings.zk_omit_ping,
        )

    def run(self, operation_name: str, callback: Callable[[Any], T], *, max_attempts: int = 3) -> T:
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            zk = self._make_zk()
            conn = None
            try:
                conn = zk.connect()
                result = callback(conn)
                return result
            except (ZKError, OSError, TimeoutError, ValueError, TypeError) as exc:
                last_exc = exc
                logger.warning(
                    "pyzk operation failed",
                    extra={
                        "operation": operation_name,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error": str(exc),
                    },
                )
                if attempt < max_attempts:
                    time.sleep(min(1.0 * (2 ** (attempt - 1)), 5.0))
            finally:
                if conn is not None:
                    try:
                        conn.disconnect()
                    except Exception:  # noqa: BLE001
                        logger.debug("pyzk disconnect failed", extra={"operation": operation_name})
        raise RuntimeError(f"pyzk operation '{operation_name}' failed after {max_attempts} attempts: {last_exc}")
