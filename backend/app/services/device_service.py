"""ZKTeco / ESSL device access via pyzk."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from zk import ZK
from zk.exception import ZKError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeviceUser:
    """Subset of pyzk User fields we persist (no biometric templates)."""

    uid: int
    name: str
    user_id: str
    privilege: int | None
    group_id: str | None
    card: str | None


@dataclass(frozen=True, slots=True)
class DeviceAttendanceRecord:
    """One raw attendance row from the device."""

    user_id: str
    timestamp: datetime
    punch: int
    status: int


class DeviceService:
    """
    TCP connection to the terminal for users and attendance.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _make_zk(self) -> ZK:
        return ZK(
            self._settings.zk_device_ip,
            port=self._settings.zk_device_port,
            timeout=self._settings.zk_device_timeout_seconds,
            password=self._settings.zk_device_password,
            force_udp=self._settings.zk_force_udp,
            ommit_ping=self._settings.zk_omit_ping,
        )

    def fetch_users(self) -> list[DeviceUser]:
        """Return users from device; empty list on failure."""
        zk = self._make_zk()
        try:
            conn = zk.connect()
            try:
                raw = conn.get_users()
            finally:
                try:
                    conn.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("disconnect after get_users: %s", exc)
        except (ZKError, OSError, TimeoutError) as exc:
            logger.warning("Device fetch_users failed: %s", exc)
            return []

        out: list[DeviceUser] = []
        for u in raw:
            uid = int(getattr(u, "uid", 0) or 0)
            name = str(getattr(u, "name", "") or "").strip() or f"User {uid}"
            user_id = getattr(u, "user_id", None)
            # user.user_id is the real attendance identity (often alphanumeric).
            user_id_str = str(user_id).strip() if user_id is not None else ""
            device_identity = user_id_str or str(uid)
            privilege_raw = getattr(u, "privilege", None)
            try:
                privilege = int(privilege_raw) if privilege_raw is not None else None
            except (TypeError, ValueError):
                privilege = None
            group_id_raw = getattr(u, "group_id", None)
            group_id = str(group_id_raw).strip() if group_id_raw not in (None, "") else None
            card_raw = getattr(u, "card", None)
            card = str(card_raw).strip() if card_raw not in (None, "") else None
            out.append(
                DeviceUser(
                    uid=uid,
                    name=name,
                    user_id=device_identity,
                    privilege=privilege,
                    group_id=group_id,
                    card=card,
                )
            )
        return out

    def check_connection(self) -> tuple[bool, str]:
        """Check if device is reachable and pyzk handshake succeeds."""
        zk = self._make_zk()
        try:
            conn = zk.connect()
            try:
                return True, "connected"
            finally:
                try:
                    conn.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("disconnect after health check: %s", exc)
        except (ZKError, OSError, TimeoutError) as exc:
            return False, str(exc)

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        """Return attendance rows from device; empty list on failure."""
        zk = self._make_zk()
        try:
            conn = zk.connect()
            try:
                raw = conn.get_attendance()
            finally:
                try:
                    conn.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("disconnect after get_attendance: %s", exc)
        except (ZKError, OSError, TimeoutError) as exc:
            logger.warning("Device fetch_attendance failed: %s", exc)
            return []

        out: list[DeviceAttendanceRecord] = []
        for row in raw:
            try:
                user_id_raw = getattr(row, "user_id", None)
                user_id = str(user_id_raw).strip() if user_id_raw is not None else ""
                if not user_id:
                    continue
                ts = getattr(row, "timestamp", None)
                if ts is None:
                    continue
                if not isinstance(ts, datetime):
                    continue
                punch = int(getattr(row, "punch", 0))
                status = int(getattr(row, "status", 0))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=ZoneInfo(self._settings.timezone))
                out.append(
                    DeviceAttendanceRecord(
                        user_id=user_id,
                        timestamp=ts,
                        punch=punch,
                        status=status,
                    )
                )
            except (TypeError, ValueError) as exc:
                logger.debug("Skipping malformed attendance row: %s (%s)", row, exc)
                continue
        return out

    def upsert_user(
        self,
        *,
        user_id: str,
        name: str,
        uid: int | None = None,
        privilege: int | None = None,
        group_id: str | None = None,
        card: str | None = None,
    ) -> None:
        """
        Create/update a user on the biometric device.

        Notes:
        - This updates user metadata only (not biometric templates).
        - If ``uid`` is omitted, we try to reuse existing uid for same user_id.
        """
        user_id = user_id.strip()
        if not user_id:
            raise ValueError("user_id is required for device upsert.")
        safe_name = name.strip() or user_id

        zk = self._make_zk()
        try:
            conn = zk.connect()
            try:
                target_uid = uid
                if target_uid is None:
                    for existing in conn.get_users():
                        existing_user_id = str(getattr(existing, "user_id", "") or "").strip()
                        if existing_user_id == user_id:
                            existing_uid_raw = getattr(existing, "uid", None)
                            if existing_uid_raw is not None:
                                target_uid = int(existing_uid_raw)
                                break
                if target_uid is None:
                    target_uid = 0

                kwargs: dict[str, object] = {
                    "uid": target_uid,
                    "name": safe_name,
                    "privilege": int(privilege or 0),
                    "user_id": user_id,
                    "group_id": group_id or "",
                    "card": int(card) if card and str(card).isdigit() else 0,
                }
                conn.set_user(**kwargs)
            finally:
                try:
                    conn.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("disconnect after upsert_user: %s", exc)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Device user upsert failed for '{user_id}': {exc}") from exc


def get_device_service(settings: Settings | None = None) -> DeviceService:
    return DeviceService(settings=settings)
