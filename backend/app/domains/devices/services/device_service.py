"""ZKTeco / ESSL device access via pyzk."""

from __future__ import annotations

import errno
import logging
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from zk import ZK
from zk.exception import ZKError

from app.core.app_timezone import as_aware
from app.core.config import Settings, get_settings
from app.core.device_clock import naive_local_wall_for_device
from app.core import device_policy
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.services.device_attlog_codec import AttlogRecord
from app.domains.devices.services.device_attlog_protocol import apply_attlog_correction, probe_attlog_capabilities
from app.shared.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported, DeviceFetchError
from app.domains.devices.services.pyzk_adapter import PyZKAdapter

logger = logging.getLogger(__name__)


def format_device_connection_error(
    exc: BaseException, *, settings: Settings | None = None, connection: DeviceConnectionConfig | None = None
) -> str:
    """Map low-level socket/pyzk failures to operator-facing sync messages."""
    if connection is not None:
        target = f"{connection.ip_address}:{connection.port}"
    else:
        cfg = settings or get_settings()
        target = f"{cfg.zk_device_ip}:{cfg.zk_device_port}"
    cfg = settings or get_settings()
    if isinstance(exc, OSError):
        if exc.errno == errno.EHOSTUNREACH:
            return (
                f"Device unreachable at {target} (no route to host). "
                "Confirm the device IP and port in Settings, then ensure nothing else is blocking TCP."
            )
        if exc.errno == errno.ECONNREFUSED:
            return (
                f"Device refused TCP connection at {target}. "
                "The terminal may have comm disabled or be using a different port."
            )
        if exc.errno == errno.ETIMEDOUT:
            return (
                f"Timed out connecting to {target}. "
                f"Try increasing ZK_DEVICE_TIMEOUT_SECONDS (currently {cfg.zk_device_timeout_seconds})."
            )
        if exc.errno == errno.EPIPE:
            return (
                f"Device dropped the connection at {target} during data transfer. "
                "Stop background Celery sync and close other ZK software, then retry."
            )
        return f"Device connection failed at {target}: {exc}"
    message = str(exc)
    if "Broken pipe" in message or "EPIPE" in message:
        return (
            f"Device dropped the connection at {target} during data transfer. "
            "Stop background Celery sync and close other ZK software, then retry."
        )
    if isinstance(exc, DeviceFetchError):
        return f"Device communication error: {exc}"
    return f"Device communication error: {exc}"

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

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        connection: DeviceConnectionConfig | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._connection = connection or DeviceConnectionConfig.from_settings(self._settings)
        self._adapter = PyZKAdapter(self._settings, connection=self._connection)
        self.last_clock_drift_seconds: float | None = None
        self.last_device_time: datetime | None = None

    @property
    def connection(self) -> DeviceConnectionConfig:
        return self._connection

    def _make_zk(self) -> ZK:
        return ZK(
            self._connection.ip_address,
            port=self._connection.port,
            timeout=self._connection.timeout_seconds,
            password=self._connection.password,
            force_udp=self._connection.force_udp,
            ommit_ping=self._connection.omit_ping,
        )

    def probe_tcp_connection(self) -> tuple[bool, str]:
        """Fast TCP reachability check without pyzk handshake."""
        try:
            with socket.create_connection(
                (self._connection.ip_address, self._connection.port),
                timeout=min(self._connection.timeout_seconds, 15),
            ):
                return True, "tcp_connected"
        except OSError as exc:
            return False, format_device_connection_error(exc, settings=self._settings, connection=self._connection)

    @staticmethod
    def safe_command_allowlist() -> set[str]:
        return {
            "UPSERT_USER",
            "CORRECT_ATTENDANCE",
            "DELETE_USER",
            "RESTART",
            "SYNC_TIME",
            "REMOTE_CONFIG",
            "REMOTE_ENROLL",
            "REMOTE_DELETE",
            "FORCE_SYNC",
            "FIRMWARE_CHECK",
        }

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

    def inspect_readonly(self) -> dict[str, Any]:
        """Read-only firmware/users probe. Never writes, deletes, or clears."""
        snapshot: dict[str, Any] = {
            "connected": False,
            "connection_detail": None,
            "firmware_version": None,
            "serial_number": None,
            "platform": None,
            "fp_version": None,
            "face_version": None,
            "users": [],
            "user_count": 0,
            "unsupported": [],
            "errors": {},
        }
        tcp_ok, tcp_detail = self.probe_tcp_connection()
        if not tcp_ok:
            snapshot["connection_detail"] = tcp_detail
            return snapshot

        def _safe_attr(conn: Any, method_name: str, field: str) -> None:
            if not hasattr(conn, method_name):
                snapshot["unsupported"].append(field)
                return
            try:
                value = getattr(conn, method_name)()
                text = str(value).strip() if value is not None else ""
                snapshot[field] = text or None
            except Exception as exc:  # noqa: BLE001
                snapshot["errors"][field] = str(exc)

        def _read(conn: Any) -> dict[str, Any]:
            for method_name in DANGEROUS_PYZK_METHODS:
                _ = hasattr(conn, method_name)
            snapshot["connected"] = True
            snapshot["connection_detail"] = "connected"
            _safe_attr(conn, "get_firmware_version", "firmware_version")
            _safe_attr(conn, "get_serialnumber", "serial_number")
            _safe_attr(conn, "get_platform", "platform")
            _safe_attr(conn, "get_fp_version", "fp_version")
            _safe_attr(conn, "get_face_version", "face_version")
            if not hasattr(conn, "get_users"):
                snapshot["unsupported"].append("users")
                return snapshot
            try:
                raw = conn.get_users() or []
                users: list[dict[str, Any]] = []
                for u in raw:
                    uid_raw = getattr(u, "uid", 0) or 0
                    try:
                        uid = int(uid_raw)
                    except (TypeError, ValueError):
                        uid = 0
                    user_id = str(getattr(u, "user_id", "") or "").strip() or str(uid)
                    privilege_raw = getattr(u, "privilege", None)
                    try:
                        privilege = int(privilege_raw) if privilege_raw is not None else None
                    except (TypeError, ValueError):
                        privilege = None
                    group_id_raw = getattr(u, "group_id", None)
                    group_id = str(group_id_raw).strip() if group_id_raw not in (None, "") else None
                    card_raw = getattr(u, "card", None)
                    card = str(card_raw).strip() if card_raw not in (None, "") else None
                    users.append(
                        {
                            "uid": uid,
                            "user_id": user_id,
                            "name": str(getattr(u, "name", "") or "").strip(),
                            "privilege": privilege,
                            "group_id": group_id,
                            "card": card,
                        }
                    )
                snapshot["users"] = users
                snapshot["user_count"] = len(users)
            except Exception as exc:  # noqa: BLE001
                snapshot["errors"]["users"] = str(exc)
            return snapshot

        try:
            self._adapter.run("inspect_readonly", _read, max_attempts=2)
        except (ZKError, OSError, TimeoutError, RuntimeError) as exc:
            snapshot["connection_detail"] = format_device_connection_error(
                exc, settings=self._settings, connection=self._connection
            )
        return snapshot

    def check_connection(self) -> tuple[bool, str]:
        """Check TCP reachability, then verify pyzk handshake succeeds."""
        tcp_ok, tcp_detail = self.probe_tcp_connection()
        if not tcp_ok:
            return False, tcp_detail
        try:
            self._adapter.run("check_connection", lambda _conn: True, max_attempts=2)
            return True, "connected"
        except (ZKError, OSError, TimeoutError) as exc:
            return False, format_device_connection_error(
                exc, settings=self._settings, connection=self._connection
            )
        except RuntimeError as exc:
            return False, format_device_connection_error(
                exc, settings=self._settings, connection=self._connection
            )

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        """Return attendance rows from device; empty list on failure.

        Same ZK session reads ``get_time`` and, when drift exceeds the configured
        threshold, writes IST wall clock before pulling attlog.
        """
        tz = ZoneInfo(self._connection.timezone)

        def _read(conn: Any) -> tuple[list[Any], float | None, datetime | None]:
            drift: float | None = None
            device_now: datetime | None = None
            if hasattr(conn, "get_time"):
                try:
                    device_now = as_aware(conn.get_time(), tz)
                    now_local = datetime.now(tz)
                    drift = (device_now - now_local).total_seconds()
                    threshold = int(self._settings.device_clock_drift_seconds)
                    if self._settings.device_auto_sync_time and abs(drift) > threshold:
                        logger.warning(
                            "Device clock drift %.0fs (threshold %ss); writing local wall clock tz=%s",
                            drift,
                            threshold,
                            self._connection.timezone,
                        )
                        wall = naive_local_wall_for_device(timezone=self._connection.timezone, now=now_local)
                        disabled = False
                        if hasattr(conn, "disable_device"):
                            conn.disable_device()
                            disabled = True
                        try:
                            if hasattr(conn, "set_time"):
                                conn.set_time(wall)
                            elif hasattr(conn, "set_device_time"):
                                conn.set_device_time(wall)
                            time.sleep(0.2)
                            if hasattr(conn, "get_time"):
                                device_now = as_aware(conn.get_time(), tz)
                                drift = (device_now - datetime.now(tz)).total_seconds()
                        finally:
                            if disabled and hasattr(conn, "enable_device"):
                                conn.enable_device()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Device get_time during attendance fetch failed: %s", exc)
            rows = conn.get_attendance()
            return list(rows or []), drift, device_now

        try:
            raw, drift, device_now = self._adapter.run("fetch_attendance", _read, max_attempts=3)
        except (ZKError, OSError, TimeoutError) as exc:
            logger.warning("Device fetch_attendance failed: %s", exc)
            raise DeviceFetchError(f"Device fetch_attendance failed: {exc}") from exc
        except RuntimeError as exc:
            logger.warning("Device fetch_attendance failed: %s", exc)
            raise DeviceFetchError(f"Device fetch_attendance failed: {exc}") from exc

        self.last_clock_drift_seconds = drift
        self.last_device_time = device_now

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
                ts = as_aware(ts, ZoneInfo(self._connection.timezone))
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

    def create_missing_users(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """CREATE-only metadata write in one device session. Never updates existing user_ids."""

        def _occupied(users: list[Any]) -> set[int]:
            occupied: set[int] = set()
            for user in users:
                try:
                    uid = int(getattr(user, "uid", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if uid > 0:
                    occupied.add(uid)
            return occupied

        def _next_uid(occupied: set[int], preferred: int | None) -> int:
            if preferred is not None and preferred > 0 and preferred not in occupied:
                return int(preferred)
            candidate = 1
            while candidate in occupied:
                candidate += 1
            return candidate

        def _write(conn: Any) -> dict[str, Any]:
            for method_name in DANGEROUS_PYZK_METHODS:
                if hasattr(conn, method_name):
                    continue
            live = list(conn.get_users() or [])
            by_id = {str(getattr(user, "user_id", "") or "").strip(): user for user in live}
            occupied = _occupied(live)
            created: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            failed: list[dict[str, Any]] = []
            total = len(rows)
            for index, row in enumerate(rows, start=1):
                user_id = str(row.get("user_id") or "").strip()
                if not user_id:
                    failed.append({"user_id": "", "error": "missing user_id"})
                    continue
                existing = by_id.get(user_id)
                if existing is not None:
                    try:
                        existing_uid = int(getattr(existing, "uid", 0) or 0) or None
                    except (TypeError, ValueError):
                        existing_uid = None
                    skipped.append({"user_id": user_id, "uid": existing_uid})
                    continue
                try:
                    preferred = row.get("uid")
                    preferred_uid = int(preferred) if preferred not in (None, "", 0, "0") else None
                except (TypeError, ValueError):
                    preferred_uid = None
                target_uid = _next_uid(occupied, preferred_uid)
                try:
                    raw_card = row.get("card")
                    card = int(raw_card) if str(raw_card or "0").isdigit() else 0
                    kwargs: dict[str, object] = {
                        "name": str(row.get("name") or user_id).strip() or user_id,
                        "privilege": int(row.get("privilege") or 0),
                        "user_id": user_id,
                        "group_id": str(row.get("group_id") or ""),
                        "card": card,
                        "uid": target_uid,
                    }
                    conn.set_user(**kwargs)
                    occupied.add(target_uid)
                    by_id[user_id] = type("User", (), {"uid": target_uid, "user_id": user_id})()
                    created.append({"user_id": user_id, "uid": target_uid})
                    if index == 1 or index == total or index % 5 == 0:
                        logger.info("Cutover CREATE %s/%s user_id=%s uid=%s", index, total, user_id, target_uid)
                    time.sleep(0.05)
                except Exception as exc:  # noqa: BLE001
                    failed.append({"user_id": user_id, "error": str(exc)})
                    logger.warning("Cutover CREATE failed user_id=%s: %s", user_id, exc)
            after = []
            for user in conn.get_users() or []:
                try:
                    uid = int(getattr(user, "uid", 0) or 0)
                except (TypeError, ValueError):
                    uid = 0
                after.append(
                    {
                        "uid": uid,
                        "user_id": str(getattr(user, "user_id", "") or "").strip(),
                        "name": str(getattr(user, "name", "") or "").strip(),
                    }
                )
            return {"created": created, "skipped": skipped, "failed": failed, "users": after}

        return self._adapter.run("create_missing_users", _write, max_attempts=2)

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
                # Never pass uid=0 — pyzk assigns next_uid when uid is omitted/None.

                existing_privilege = int(getattr(existing_user, "privilege", 0) or 0) if existing_user is not None else 0
                existing_group_id = str(getattr(existing_user, "group_id", "") or "") if existing_user is not None else ""
                existing_card = str(getattr(existing_user, "card", "") or "") if existing_user is not None else ""

                effective_privilege = int(privilege) if privilege is not None else existing_privilege
                effective_group_id = (group_id if group_id is not None else existing_group_id) or ""
                raw_card = card if card is not None else existing_card
                effective_card = int(raw_card) if str(raw_card).isdigit() else 0

                kwargs: dict[str, object] = {
                    "name": safe_name,
                    "privilege": effective_privilege,
                    "user_id": user_id,
                    "group_id": effective_group_id,
                    "card": effective_card,
                }
                if target_uid is not None and int(target_uid) > 0:
                    kwargs["uid"] = int(target_uid)
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

    def resolve_uid_for_user_id(self, user_id: str) -> int | None:
        """Return device uid for a user_id, or None if absent on device."""
        normalized = user_id.strip()
        if not normalized:
            return None
        for user in self.fetch_users():
            if user.user_id.strip() == normalized:
                return int(user.uid)
        return None

    def delete_user(self, *, uid: int | None = None, user_id: str | None = None) -> None:
        """Remove a user (and biometric template) from the device."""
        target_uid = int(uid) if uid is not None else None
        normalized_user_id = (user_id or "").strip()
        if (target_uid is None or target_uid <= 0) and normalized_user_id:
            target_uid = self.resolve_uid_for_user_id(normalized_user_id)
        if target_uid is None or target_uid <= 0:
            raise ValueError("uid is required for device delete (user not found on device).")

        try:
            def _delete(conn: Any) -> None:
                conn.delete_user(uid=target_uid)
                time.sleep(0.1)

            self._adapter.run("delete_user", _delete, max_attempts=2)
        except Exception as exc:  # noqa: BLE001
            identity = normalized_user_id or str(target_uid)
            raise RuntimeError(f"Device user delete failed for '{identity}': {exc}") from exc

    def verify_user_deleted(self, *, user_id: str) -> tuple[bool, dict[str, Any]]:
        """Confirm user_id is absent from device after delete."""
        normalized = user_id.strip()
        users = self.fetch_users()
        match = next((u for u in users if u.user_id.strip() == normalized), None)
        if match is None:
            return True, {
                "expected_state": {"user_id": normalized, "present": False},
                "actual_state": None,
                "mismatch_details": None,
            }
        return False, {
            "expected_state": {"user_id": normalized, "present": False},
            "actual_state": {
                "user_id": match.user_id.strip(),
                "uid": int(match.uid),
                "name": match.name.strip(),
            },
            "mismatch_details": {"reason": "user_still_present_after_delete"},
        }

    def probe_attlog_capabilities(self) -> dict[str, object]:
        def _probe(conn: Any) -> dict[str, object]:
            caps = probe_attlog_capabilities(conn, allow_tier_b_write=device_policy.ATTLOG_TIER_B_REWRITE)
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
                tz_name=self._connection.timezone,
                allow_tier_b_write=device_policy.ATTLOG_TIER_B_REWRITE,
            )

        try:
            return self._adapter.run("correct_attendance", _correct, max_attempts=2)
        except AttlogCorrectionNotSupported:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AttlogCorrectionError(f"Device attlog correction failed: {exc}") from exc

    def restart_device(self) -> None:
        """Remotely restart the biometric terminal."""

        def _restart(conn: Any) -> None:
            if not hasattr(conn, "restart"):
                raise RuntimeError("Device firmware does not support remote restart.")
            conn.restart()

        self._adapter.run("restart_device", _restart, max_attempts=1)

    def sync_device_time(self) -> datetime:
        """Synchronize the terminal wall clock to the configured local timezone.

        ZKTeco ``set_time`` writes naive year/month/day/hour components. Passing UTC
        makes Monday 09:00 IST land on the device as 03:30, which this app then
        tags as local and stores as Sunday night.
        """

        def _sync(conn: Any) -> datetime:
            tz = ZoneInfo(self._connection.timezone)
            now_local = datetime.now(tz)
            wall = naive_local_wall_for_device(timezone=self._connection.timezone, now=now_local)
            disabled = False
            if hasattr(conn, "disable_device"):
                conn.disable_device()
                disabled = True
            try:
                if hasattr(conn, "set_time"):
                    ok = conn.set_time(wall)
                    if ok is False:
                        raise RuntimeError("Device set_time returned False.")
                elif hasattr(conn, "set_device_time"):
                    conn.set_device_time(wall)
                else:
                    raise RuntimeError("Device firmware does not support time synchronization.")
                time.sleep(0.2)
                if hasattr(conn, "get_time"):
                    device_now = as_aware(conn.get_time(), tz)
                    drift = (device_now - datetime.now(tz)).total_seconds()
                    self.last_clock_drift_seconds = drift
                    self.last_device_time = device_now
                    if abs(drift) > 120:
                        logger.warning(
                            "Device clock drift after sync is %.0fs (wrote=%s read=%s device=%s tz=%s)",
                            drift,
                            wall.isoformat(),
                            device_now.replace(tzinfo=None).isoformat(),
                            self._connection.device_id,
                            self._connection.timezone,
                        )
            finally:
                if disabled and hasattr(conn, "enable_device"):
                    conn.enable_device()
            return now_local

        return self._adapter.run("sync_device_time", _sync, max_attempts=2)

    def apply_remote_config(self, config: dict[str, object]) -> dict[str, object]:
        """Apply non-destructive remote configuration where supported by firmware."""
        applied: dict[str, object] = {}

        def _apply(conn: Any) -> dict[str, object]:
            if "timezone" in config and hasattr(conn, "set_timezone"):
                raw_tz = str(config["timezone"]).strip()
                # Firmware expects a numeric GMT offset (minutes), not IANA names.
                if "/" in raw_tz or not raw_tz.lstrip("+-").isdigit():
                    logger.warning("Skipping firmware set_timezone for non-numeric value %r", raw_tz)
                else:
                    conn.set_timezone(raw_tz)
                    applied["timezone"] = raw_tz
            if "volume" in config and hasattr(conn, "set_volume"):
                conn.set_volume(int(config["volume"]))
                applied["volume"] = config["volume"]
            if "voice" in config and hasattr(conn, "set_voice"):
                conn.set_voice(bool(config["voice"]))
                applied["voice"] = config["voice"]
            return applied

        return self._adapter.run("apply_remote_config", _apply, max_attempts=2)


def get_device_service(settings: Settings | None = None) -> DeviceService:
    """Bootstrap/CLI helper using env connection.

    Prefer ``device_service_for(db)`` for runtime paths so Settings/DB IP is used.
    """
    return DeviceService(settings=settings)
