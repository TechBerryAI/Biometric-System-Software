"""ADMS push protocol connector for inbound device communication."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.gateway.base import DeviceConnector
from app.domains.devices.services.device_service import DeviceAttendanceRecord, DeviceUser

logger = logging.getLogger(__name__)


class PushConnector(DeviceConnector):
    """Processes push payloads buffered from ADMS inbound requests."""

    def __init__(self, connection: DeviceConnectionConfig, offline_buffer: dict[str, Any] | None = None) -> None:
        self._connection = connection
        self._buffer = offline_buffer or {}

    @property
    def connection(self) -> DeviceConnectionConfig:
        return self._connection

    def check_connection(self) -> tuple[bool, str]:
        last_push = self._buffer.get("last_push_at")
        if last_push:
            return True, f"last_push_at={last_push}"
        return False, "no_push_received"

    def fetch_users(self) -> list[DeviceUser]:
        users_raw = self._buffer.get("users") or []
        out: list[DeviceUser] = []
        for row in users_raw:
            if not isinstance(row, dict):
                continue
            user_id = str(row.get("user_id") or row.get("pin") or "").strip()
            if not user_id:
                continue
            out.append(
                DeviceUser(
                    uid=int(row.get("uid") or 0),
                    name=str(row.get("name") or user_id),
                    user_id=user_id,
                    privilege=row.get("privilege"),
                    group_id=row.get("group_id"),
                    card=row.get("card"),
                )
            )
        return out

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        records_raw = self._buffer.get("attendance") or []
        out: list[DeviceAttendanceRecord] = []
        tz = ZoneInfo(self._connection.timezone)
        for row in records_raw:
            if not isinstance(row, dict):
                continue
            user_id = str(row.get("user_id") or row.get("pin") or "").strip()
            ts_raw = row.get("timestamp") or row.get("time")
            if not user_id or not ts_raw:
                continue
            try:
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.fromtimestamp(float(ts_raw), tz=ZoneInfo("UTC"))
                else:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=tz)
            except (TypeError, ValueError):
                continue
            out.append(
                DeviceAttendanceRecord(
                    user_id=user_id,
                    timestamp=ts,
                    punch=int(row.get("punch") or 0),
                    status=int(row.get("status") or 0),
                )
            )
        return out

    def ingest_push_payload(self, payload: dict[str, Any]) -> dict[str, int]:
        """Merge inbound ADMS payload into offline buffer."""
        if "users" in payload and isinstance(payload["users"], list):
            existing = list(self._buffer.get("users") or [])
            existing.extend(payload["users"])
            self._buffer["users"] = existing
        if "attendance" in payload and isinstance(payload["attendance"], list):
            existing = list(self._buffer.get("attendance") or [])
            existing.extend(payload["attendance"])
            self._buffer["attendance"] = existing
        self._buffer["last_push_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
        return {
            "users_buffered": len(payload.get("users") or []),
            "attendance_buffered": len(payload.get("attendance") or []),
        }

    def clear_buffer(self) -> None:
        self._buffer = {}

    @property
    def buffer(self) -> dict[str, Any]:
        return self._buffer
