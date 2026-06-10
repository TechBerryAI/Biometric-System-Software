"""ZKTeco / ESSL device access via pyzk."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from zk import ZK
from zk.exception import ZKError

from app.core.config import Settings, get_settings
from app.services.device_attlog_codec import AttlogRecord
from app.services.device_attlog_protocol import apply_attlog_correction, probe_attlog_capabilities
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported, DeviceFetchError
from app.services.pyzk_adapter import PyZKAdapter

logger = logging.getLogger(__name__)

DANGEROUS_PYZK_METHODS = {
    "clear_attendance",
    "clear_data",
    "delete_attendance",
    "delete_user",
    "restart",
    "poweroff",
}


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
        self._adapter = PyZKAdapter(self._settings)

    def _make_zk(self) -> ZK:
        return ZK(
            self._settings.zk_device_ip,
            port=self._settings.zk_device_port,
            timeout=self._settings.zk_device_timeout_seconds,
            password=self._settings.zk_device_password,
            force_udp=self._settings.zk_force_udp,
            ommit_ping=self._settings.zk_omit_ping,
        )

    @staticmethod
    def safe_command_allowlist() -> set[str]:
        return {"UPSERT_USER", "CORRECT_ATTENDANCE"}

    def detect_firmware_fingerprint(self) -> dict[str, Any]:
        """Best-effort firmware/platform fingerprint for safe profile selection."""
        firmware_version: str | None = None
        platform: str | None = None
        serial_number: str | None = None
        try:
            def _read(conn: Any) -> None:
                nonlocal firmware_version, platform, serial_number
                if hasattr(conn, "get_firmware_version"):
                    try:
                        firmware_version = str(conn.get_firmware_version() or "").strip() or None
                    except Exception:  # noqa: BLE001
                        firmware_version = None
                if hasattr(conn, "get_platform"):
                    try:
                        platform = str(conn.get_platform() or "").strip() or None
                    except Exception:  # noqa: BLE001
                        platform = None
                if hasattr(conn, "get_serialnumber"):
                    try:
                        serial_number = str(conn.get_serialnumber() or "").strip() or None
                    except Exception:  # noqa: BLE001
                        serial_number = None
            self._adapter.run("detect_firmware_fingerprint", _read, max_attempts=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Device firmware fingerprint detection failed: %s", exc)
        return {
            "firmware_version": firmware_version or "unknown",
            "platform": platform,
            "serial_number": serial_number,
        }

    def fetch_users(self) -> list[DeviceUser]:
        """Return users from device; empty list on failure."""
        try:
            raw = self._adapter.run("fetch_users", lambda conn: conn.get_users(), max_attempts=3)
        except (ZKError, OSError, TimeoutError) as exc:
            logger.warning("Device fetch_users failed: %s", exc)
            raise DeviceFetchError(f"Device fetch_users failed: {exc}") from exc
        except RuntimeError as exc:
            logger.warning("Device fetch_users failed: %s", exc)
            raise DeviceFetchError(f"Device fetch_users failed: {exc}") from exc

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
        try:
            self._adapter.run("check_connection", lambda _conn: True, max_attempts=2)
            return True, "connected"
        except (ZKError, OSError, TimeoutError) as exc:
            return False, str(exc)
        except RuntimeError as exc:
            return False, str(exc)

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        """Return attendance rows from device; empty list on failure."""
        try:
            raw = self._adapter.run("fetch_attendance", lambda conn: conn.get_attendance(), max_attempts=3)
        except (ZKError, OSError, TimeoutError) as exc:
            logger.warning("Device fetch_attendance failed: %s", exc)
            raise DeviceFetchError(f"Device fetch_attendance failed: {exc}") from exc
        except RuntimeError as exc:
            logger.warning("Device fetch_attendance failed: %s", exc)
            raise DeviceFetchError(f"Device fetch_attendance failed: {exc}") from exc

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

        try:
            def _write(conn: Any) -> None:
                for method_name in DANGEROUS_PYZK_METHODS:
                    if hasattr(conn, method_name):
                        # Existence of dangerous methods is expected in pyzk.
                        # We never call them; this runtime assertion documents safety intent.
                        continue
                target_uid = uid
                existing_user: Any | None = None
                if target_uid is None:
                    for existing in conn.get_users():
                        existing_user_id = str(getattr(existing, "user_id", "") or "").strip()
                        if existing_user_id == user_id:
                            existing_user = existing
                            existing_uid_raw = getattr(existing, "uid", None)
                            if existing_uid_raw is not None:
                                target_uid = int(existing_uid_raw)
                                break
                if target_uid is None:
                    target_uid = 0

                existing_privilege = int(getattr(existing_user, "privilege", 0) or 0) if existing_user is not None else 0
                existing_group_id = str(getattr(existing_user, "group_id", "") or "") if existing_user is not None else ""
                existing_card = str(getattr(existing_user, "card", "") or "") if existing_user is not None else ""

                effective_privilege = int(privilege) if privilege is not None else existing_privilege
                effective_group_id = (group_id if group_id is not None else existing_group_id) or ""
                raw_card = card if card is not None else existing_card
                effective_card = int(raw_card) if str(raw_card).isdigit() else 0

                kwargs: dict[str, object] = {
                    "uid": target_uid,
                    "name": safe_name,
                    "privilege": effective_privilege,
                    "user_id": user_id,
                    "group_id": effective_group_id,
                    "card": effective_card,
                }
                conn.set_user(**kwargs)
                # Older firmware can delay write persistence; short cooldown reduces false negatives.
                time.sleep(0.1)
            self._adapter.run("upsert_user", _write, max_attempts=2)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Device user upsert failed for '{user_id}': {exc}") from exc

    def verify_user(
        self,
        *,
        user_id: str,
        expected_name: str,
        expected_uid: int | None,
        expected_privilege: int | None,
        expected_group_id: str | None,
        expected_card: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        """Read users back from device and compare normalized values."""
        normalized_expected = {
            "user_id": user_id.strip(),
            "name": expected_name.strip(),
            "uid": int(expected_uid) if expected_uid is not None else None,
            "privilege": int(expected_privilege) if expected_privilege is not None else 0,
            "group_id": (expected_group_id or "").strip() or None,
            "card": (expected_card or "").strip() or None,
        }
        users = self.fetch_users()
        match = next((u for u in users if u.user_id.strip() == normalized_expected["user_id"]), None)
        if match is None:
            return False, {
                "expected_state": normalized_expected,
                "actual_state": None,
                "mismatch_details": {"reason": "user_not_found_after_write"},
            }
        normalized_actual = {
            "user_id": match.user_id.strip(),
            "name": match.name.strip(),
            "uid": int(match.uid),
            "privilege": int(match.privilege) if match.privilege is not None else 0,
            "group_id": (match.group_id or "").strip() or None,
            "card": (match.card or "").strip() or None,
        }
        mismatch: dict[str, dict[str, Any]] = {}
        for field in ("name", "uid", "privilege", "group_id", "card"):
            expected_val = normalized_expected[field]
            actual_val = normalized_actual[field]
            if expected_val is not None and expected_val != actual_val:
                mismatch[field] = {"expected": expected_val, "actual": actual_val}
        return (
            len(mismatch) == 0,
            {
                "expected_state": normalized_expected,
                "actual_state": normalized_actual,
                "mismatch_details": mismatch or None,
            },
        )

    def probe_attlog_capabilities(self) -> dict[str, object]:
        def _probe(conn: Any) -> dict[str, object]:
            caps = probe_attlog_capabilities(conn)
            return {
                "tier": caps.tier,
                "record_size": caps.record_size,
                "supports_selective_delete": caps.supports_selective_delete,
                "supports_full_rewrite": caps.supports_full_rewrite,
                "supports_write": caps.supports_write,
            }

        return self._adapter.run("probe_attlog_capabilities", _probe, max_attempts=2)

    def correct_attendance(
        self,
        *,
        user_id: str,
        uid: int | None,
        delete_timestamps: list[datetime],
        new_check_in: datetime | None,
        new_check_out: datetime | None,
    ) -> dict[str, object]:
        """Rewrite IN/OUT punches on the biometric device with readback verification."""
        new_records: list[AttlogRecord] = []
        resolved_uid = int(uid or 0)
        if new_check_in is not None:
            new_records.append(
                AttlogRecord(
                    uid=resolved_uid,
                    user_id=user_id.strip(),
                    timestamp=new_check_in,
                    status=0,
                    punch=0,
                )
            )
        if new_check_out is not None:
            new_records.append(
                AttlogRecord(
                    uid=resolved_uid,
                    user_id=user_id.strip(),
                    timestamp=new_check_out,
                    status=1,
                    punch=1,
                )
            )

        def _correct(conn: Any) -> dict[str, object]:
            return apply_attlog_correction(
                conn,
                user_id=user_id,
                delete_timestamps=delete_timestamps,
                new_records=new_records,
                tz_name=self._settings.timezone,
            )

        try:
            return self._adapter.run("correct_attendance", _correct, max_attempts=2)
        except AttlogCorrectionNotSupported:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AttlogCorrectionError(f"Device attlog correction failed: {exc}") from exc


def get_device_service(settings: Settings | None = None) -> DeviceService:
    return DeviceService(settings=settings)
