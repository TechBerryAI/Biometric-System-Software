"""Defensive pyzk adapter with reconnect/timeouts containment."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from zk import ZK
from zk.exception import ZKError

from app.core.config import Settings
from app.domains.devices.connection import DeviceConnectionConfig

logger = logging.getLogger(__name__)
T = TypeVar("T")


class PyZKAdapter:
    """Isolate unstable pyzk behavior behind bounded retries and parsing guards."""

    def __init__(self, settings: Settings | None = None, *, connection: DeviceConnectionConfig | None = None) -> None:
        self._settings = settings
        self._connection = connection

    def _resolve_connection(self) -> DeviceConnectionConfig:
        if self._connection is not None:
            return self._connection
        from app.core.config import get_settings

        return DeviceConnectionConfig.from_settings(self._settings or get_settings())

    def _make_zk(self) -> ZK:
        conn = self._resolve_connection()
        return ZK(
            conn.ip_address,
            port=conn.port,
            timeout=conn.timeout_seconds,
            password=conn.password,
            force_udp=conn.force_udp,
            ommit_ping=conn.omit_ping,
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
