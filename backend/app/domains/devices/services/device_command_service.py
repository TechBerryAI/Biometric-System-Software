"""Queueing and execution helpers for safe device commands."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from redis import Redis
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core import device_policy
from app.core.operator_access import is_operator_account
from app.core.redis_keys import with_namespace
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.devices.models.device import Device
from app.domains.auth.models.user import User
from app.shared.device_exceptions import DeviceLockContentionError
from app.domains.devices.services.device_service import DeviceService
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.ops.services.system_governance_service import assert_device_write_allowed

logger = logging.getLogger(__name__)

INTERNAL_COMMAND_TYPES = frozenset({"CORRECT_ATTENDANCE"})
_CORRECTION_ACTIVE_STATUSES = frozenset(
    {
        DeviceCommandStatus.PENDING.value,
        DeviceCommandStatus.RUNNING.value,
        DeviceCommandStatus.RETRYING.value,
        DeviceCommandStatus.VERIFYING.value,
    }
)


def _append_status_history(command: DeviceCommand, status: str, *, detail: str | None = None) -> None:
    history = list(command.status_history or [])
    entry: dict[str, Any] = {"status": status, "at": _utcnow().isoformat()}
    if detail:
        entry["detail"] = detail
    history.append(entry)
    # Keep last 50 transitions to bound JSON growth.
    command.status_history = history[-50:]


def device_has_active_correction_commands(db: Session, device_id: str) -> bool:
    """True when a CORRECT_ATTENDANCE command is queued or executing for this device."""
    row = db.execute(
        select(DeviceCommand.id)
        .where(
            DeviceCommand.device_id == device_id,
            DeviceCommand.command_type == "CORRECT_ATTENDANCE",
            DeviceCommand.status.in_(_CORRECTION_ACTIVE_STATUSES),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def drain_due_correction_commands(
    db: Session,
    device_id: str,
    *,
    settings: Settings | None = None,
    worker_id: str = "inline-drain",
) -> int:
    """Process due PENDING/RETRYING CORRECT_ATTENDANCE commands inline (dev without Celery)."""
    settings = settings or get_settings()
    now = _utcnow()
    commands = list(
        db.execute(
            select(DeviceCommand)
            .where(
                DeviceCommand.device_id == device_id,
                DeviceCommand.command_type == "CORRECT_ATTENDANCE",
                DeviceCommand.status.in_(
                    [DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value]
                ),
                or_(DeviceCommand.next_attempt_at.is_(None), DeviceCommand.next_attempt_at <= now),
            )
            .order_by(DeviceCommand.created_at.asc())
        ).scalars().all()
    )
    processed = 0
    for command in commands:
        try:
            process_command(db, command, settings=settings, worker_id=worker_id)
            db.commit()
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Inline correction drain failed for %s: %s", command.command_uuid, exc)
            db.rollback()
    return processed


def wait_for_correction_commands_clear(
    db: Session,
    device_id: str,
    *,
    settings: Settings | None = None,
    max_wait_seconds: float | None = None,
) -> bool:
    """
    Wait until no CORRECT_ATTENDANCE commands are active for the device.

    Returns True when the device is clear (or was already clear); False if still busy
    after max_wait_seconds.
    """
    settings = settings or get_settings()
    drain_due_correction_commands(db, device_id, settings=settings)
    if not device_has_active_correction_commands(db, device_id):
        return True
    deadline = time.monotonic() + (
        max_wait_seconds if max_wait_seconds is not None else float(settings.command_lock_blocking_seconds)
    )
    while time.monotonic() < deadline:
        time.sleep(1.0)
        db.expire_all()
        drain_due_correction_commands(db, device_id, settings=settings)
        if not device_has_active_correction_commands(db, device_id):
            return True
    return not device_has_active_correction_commands(db, device_id)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _idempotency_key(device_id: str, command_type: str, payload: dict[str, Any]) -> str:
    canonical = f"{device_id}:{command_type}:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _execution_hash(command: DeviceCommand, attempt: int) -> str:
    canonical = (
        f"{command.device_id}:{command.command_type}:"
        f"{json.dumps(command.payload, sort_keys=True, separators=(',', ':'))}:{attempt}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_key(device_id: str, settings: Settings) -> str:
    return with_namespace(settings.redis_namespace, f"device:lock:{device_id}")


class _LocalDeviceLock:
    """In-process mutex when Redis is unavailable (single-worker dev)."""

    _registry: dict[str, threading.Lock] = {}
    _registry_guard = threading.Lock()

    def __init__(self, key: str) -> None:
        with self._registry_guard:
            if key not in self._registry:
                self._registry[key] = threading.Lock()
            self._mutex = self._registry[key]
        self._held = False

    def acquire(self, blocking: bool = True, blocking_timeout: float | None = None) -> bool:
        if blocking_timeout is not None:
            deadline = time.monotonic() + blocking_timeout
            while True:
                if self._mutex.acquire(blocking=False):
                    self._held = True
                    return True
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.05)
        self._held = self._mutex.acquire(blocking=blocking)
        return self._held

    def release(self) -> None:
        if self._held:
            self._mutex.release()
            self._held = False

    def extend(self, *_args: Any, **_kwargs: Any) -> bool:
        return self._held


def _acquire_local_lock(key: str, *, blocking_timeout: float = 15) -> _LocalDeviceLock | None:
    lock = _LocalDeviceLock(key)
    if lock.acquire(blocking=True, blocking_timeout=blocking_timeout):
        return lock
    return None


class _LockHeartbeat:
    def __init__(self, lock: Any, *, period_seconds: int, extension_seconds: int) -> None:
        self._lock = lock
        self._period_seconds = period_seconds
        self._extension_seconds = extension_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="device-lock-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self._period_seconds + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._period_seconds):
            try:
                self._lock.extend(self._extension_seconds)
            except Exception:  # noqa: BLE001
                # Let stale-command recovery handle lock/session interruption.
                return


def enqueue_device_command(
    db: Session,
    *,
    device_id: str,
    command_type: str,
    payload: dict[str, Any],
    correlation_id: str | None,
    created_by: str | None,
    initiated_from: str | None = "api",
) -> DeviceCommand:
    if not device_policy.DEVICE_WRITES_ENABLED:
        raise RuntimeError("Device write operations are disabled by policy.")
    allowed, reason = assert_device_write_allowed(db, device_id=device_id)
    if not allowed:
        raise RuntimeError(reason or "Device writes are blocked by governance policy.")
    allowlist = DeviceService.safe_command_allowlist()
    if command_type not in allowlist:
        raise RuntimeError(f"Rejected unsafe command type '{command_type}'.")
    if command_type in INTERNAL_COMMAND_TYPES:
        if not created_by:
            raise RuntimeError("CORRECT_ATTENDANCE requires an authenticated operator.")
        actor = db.execute(select(User).where(User.user_uuid == created_by)).scalar_one_or_none()
        if not is_operator_account(actor):
            raise RuntimeError("CORRECT_ATTENDANCE is restricted to the operator account.")
    key = _idempotency_key(device_id, command_type, payload)
    existing = db.execute(
        select(DeviceCommand).where(
            DeviceCommand.idempotency_key == key,
            DeviceCommand.status.in_(
                [
                    DeviceCommandStatus.PENDING.value,
                    DeviceCommandStatus.RUNNING.value,
                    DeviceCommandStatus.RETRYING.value,
                    DeviceCommandStatus.VERIFYING.value,
                ]
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    command = DeviceCommand(
        device_id=device_id,
        command_type=command_type,
        payload=payload,
        status=DeviceCommandStatus.PENDING.value,
        correlation_id=correlation_id,
        initiated_by=created_by,
        initiated_from=initiated_from,
        idempotency_key=key,
        retry_backoff_seconds=0,
        verification_status=None,
        verification_details=None,
        next_attempt_at=_utcnow(),
        status_history=[{"status": DeviceCommandStatus.PENDING.value, "at": _utcnow().isoformat()}],
    )
    db.add(command)
    db.flush()
    # Extend audit trail for enroll/delete and other device writes.
    try:
        from app.domains.audit.services.audit_service import record_audit_event
        from app.domains.auth.models.user import User as AuthUser

        actor = None
        if created_by:
            actor = db.execute(select(AuthUser).where(AuthUser.user_uuid == created_by)).scalar_one_or_none()
        event = record_audit_event(
            db,
            action=f"device_command.{command_type.lower()}",
            actor=actor,
            resource_type="device_command",
            resource_id=command.command_uuid,
            metadata={
                "device_id": device_id,
                "command_type": command_type,
                "initiated_from": initiated_from,
            },
        )
        command.audit_event_uuid = event.event_uuid
        db.flush()
    except Exception:  # noqa: BLE001
        logger.debug("device_command audit recording skipped", exc_info=True)
    return command


def reprocess_device_command(
    db: Session,
    command_uuid: str,
    *,
    settings: Settings | None = None,
    worker_id: str = "api-reprocess",
) -> DeviceCommand:
    """Run inline processing for a queued command (e.g. stuck PENDING after API timeout)."""
    command = db.execute(
        select(DeviceCommand).where(DeviceCommand.command_uuid == command_uuid)
    ).scalar_one_or_none()
    if command is None:
        raise ValueError("Device command not found.")
    if command.status not in (
        DeviceCommandStatus.PENDING.value,
        DeviceCommandStatus.RETRYING.value,
        DeviceCommandStatus.FAILED.value,
    ):
        return command
    process_command(db, command, settings=settings, worker_id=worker_id)
    db.commit()
    db.refresh(command)
    return command


def claim_pending_commands(db: Session, *, settings: Settings | None = None) -> list[DeviceCommand]:
    settings = settings or get_settings()
    now = _utcnow()
    query = (
        select(DeviceCommand)
        .where(
            DeviceCommand.status.in_([DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value]),
            or_(DeviceCommand.next_attempt_at.is_(None), DeviceCommand.next_attempt_at <= now),
        )
        .order_by(DeviceCommand.created_at.asc())
        .limit(settings.command_queue_batch_size)
        .with_for_update(skip_locked=True)
    )
    commands = list(db.execute(query).scalars().all())
    commands.sort(key=lambda c: (0 if c.command_type == "CORRECT_ATTENDANCE" else 1, c.created_at or now))
    runnable: list[DeviceCommand] = []
    seen_devices: set[str] = set()
    for command in commands:
        if command.device_id in seen_devices:
            # Preserve ordering by leaving later commands pending for next claim cycle.
            continue
        seen_devices.add(command.device_id)
        command.status = DeviceCommandStatus.RUNNING.value
        command.started_at = command.started_at or now
        command.heartbeat_at = now
        runnable.append(command)
    return runnable


def _acquire_lock(
    device_id: str,
    settings: Settings,
    *,
    blocking_timeout: float | None = None,
) -> tuple[Redis | None, Any, str]:
    key = _lock_key(device_id, settings)
    lock_wait_seconds = blocking_timeout if blocking_timeout is not None else max(settings.command_lock_blocking_seconds, 15)
    try:
        client = Redis.from_url(str(settings.redis_url), socket_timeout=2, socket_connect_timeout=2)
        lock_timeout = settings.zk_device_timeout_seconds + settings.command_heartbeat_seconds + 10
        lock = client.lock(key, timeout=lock_timeout, blocking_timeout=lock_wait_seconds)
        if lock.acquire(blocking=True, blocking_timeout=lock_wait_seconds):
            return client, lock, key
        logger.warning("Redis device lock busy for device_id=%s key=%s", device_id, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Redis device lock unavailable for device_id=%s (%s); using in-process fallback",
            device_id,
            exc,
        )
        local = _acquire_local_lock(key, blocking_timeout=lock_wait_seconds)
        if local is not None:
            return None, local, key
    return None, None, key


@contextmanager
def device_session_lock(
    device_id: str,
    settings: Settings | None = None,
    *,
    blocking_timeout: float | None = None,
) -> Iterator[None]:
    """
    Serialize all device I/O (sync reads and command writes) for a single terminal.
    ZKTeco devices typically accept only one TCP client at a time.
    """
    settings = settings or get_settings()
    wait_seconds = blocking_timeout if blocking_timeout is not None else max(settings.command_lock_blocking_seconds, 30)
    client, lock, lock_key = _acquire_lock(device_id, settings, blocking_timeout=wait_seconds)
    if lock is None:
        raise DeviceLockContentionError(
            f"Device '{device_id}' is busy (another sync or write is in progress). Wait a few seconds and retry."
        )
    lock_heartbeat = _LockHeartbeat(
        lock,
        period_seconds=settings.command_heartbeat_seconds,
        extension_seconds=settings.zk_device_timeout_seconds + settings.command_heartbeat_seconds + 10,
    )
    lock_heartbeat.start()
    try:
        yield
    finally:
        lock_heartbeat.stop()
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.debug("redis client close failed for device lock key=%s", lock_key)


def _enforce_safe_write_policy(
    *,
    payload: dict[str, Any],
    current_on_device: dict[str, Any] | None,
    settings: Settings | None = None,
) -> tuple[bool, str | None]:
    _ = settings  # kept for call-site compatibility; policy lives in device_policy
    override = bool(payload.get("admin_override"))
    if override and not device_policy.ADMIN_OVERRIDE:
        return False, "admin override is disabled by policy"

    def _changed(field: str) -> bool:
        if current_on_device is None:
            return False
        proposed = payload.get(field)
        if proposed is None:
            return False
        current = current_on_device.get(field)
        if current is None:
            return True
        return str(proposed).strip() != str(current).strip()

    if _changed("uid"):
        if not device_policy.UID_REWRITE and not override:
            return False, "uid rewrite blocked by safety policy"
    if _changed("privilege"):
        if not device_policy.PRIVILEGE_UPDATE and not override:
            return False, "privilege rewrite blocked by safety policy"
    if _changed("card"):
        if not device_policy.CARD_REWRITE and not override:
            return False, "card rewrite blocked by safety policy"
    return True, None


def _verify_upsert_result(
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
) -> bool:
    ok, details = device_service.verify_user(
        user_id=str(payload["user_id"]),
        expected_name=str(payload["name"]),
        expected_uid=payload.get("uid"),
        expected_privilege=payload.get("privilege"),
        expected_group_id=payload.get("group_id"),
        expected_card=str(payload.get("card")) if payload.get("card") is not None else None,
    )
    command.verification_status = "SUCCESS" if ok else "FAILED"
    command.verification_details = details
    return ok


def _verify_delete_result(
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
) -> bool:
    ok, details = device_service.verify_user_deleted(user_id=str(payload["user_id"]))
    command.verification_status = "SUCCESS" if ok else "FAILED"
    command.verification_details = details
    return ok


def _recover_if_already_applied(
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
) -> bool:
    ok, details = device_service.verify_user(
        user_id=str(payload["user_id"]),
        expected_name=str(payload["name"]),
        expected_uid=payload.get("uid"),
        expected_privilege=payload.get("privilege"),
        expected_group_id=payload.get("group_id"),
        expected_card=str(payload.get("card")) if payload.get("card") is not None else None,
    )
    if not ok:
        return False
    command.status = DeviceCommandStatus.SUCCESS.value
    command.completed_at = _utcnow()
    command.last_error = None
    command.verification_status = "SUCCESS"
    command.verification_details = details
    return True


def _recover_if_delete_already_applied(
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
) -> bool:
    ok, details = device_service.verify_user_deleted(user_id=str(payload["user_id"]))
    if not ok:
        return False
    command.status = DeviceCommandStatus.SUCCESS.value
    command.completed_at = _utcnow()
    command.last_error = None
    command.verification_status = "SUCCESS"
    command.verification_details = details
    return True


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _execute_correct_attendance_command(
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
) -> None:
    delete_ts = [_parse_iso_datetime(ts) for ts in payload.get("delete_timestamps", [])]
    new_in_raw = payload.get("new_check_in")
    new_out_raw = payload.get("new_check_out")
    new_check_in = _parse_iso_datetime(new_in_raw) if new_in_raw else None
    new_check_out = _parse_iso_datetime(new_out_raw) if new_out_raw else None
    if new_check_in is None:
        raise ValueError("new_check_in is required for CORRECT_ATTENDANCE.")
    result = device_service.correct_attendance(
        user_id=str(payload["user_id"]),
        uid=payload.get("uid"),
        delete_timestamps=delete_ts,
        new_check_in=new_check_in,
        new_check_out=new_check_out,
    )
    command.status = DeviceCommandStatus.SUCCESS.value
    command.completed_at = _utcnow()
    command.verification_status = "SUCCESS"
    command.verification_details = result
    command.last_error = None


def _mark_retry_or_terminal(command: DeviceCommand, *, settings: Settings, error_message: str) -> None:
    command.retries += 1
    command.last_error = error_message[:2000]
    if command.retries >= settings.command_max_retries:
        command.status = DeviceCommandStatus.DEAD_LETTER.value
        command.completed_at = _utcnow()
        return
    delay = min(
        settings.command_retry_base_seconds * (2 ** (command.retries - 1)),
        settings.command_retry_max_seconds,
    )
    command.retry_backoff_seconds = int(delay)
    command.status = DeviceCommandStatus.RETRYING.value
    command.next_attempt_at = _utcnow() + timedelta(seconds=delay)


def _find_current_user_on_device(
    device_service: DeviceService,
    *,
    user_id: str,
) -> dict[str, Any] | None:
    for user in device_service.fetch_users():
        if str(user.user_id or "").strip() == user_id.strip():
            return {
                "user_id": user.user_id,
                "name": user.name,
                "uid": user.uid,
                "privilege": user.privilege,
                "group_id": user.group_id,
                "card": user.card,
            }
    return None


def _mark_correction_failed_if_needed(db: Session, command: DeviceCommand, *, error_message: str) -> None:
    if command.command_type != "CORRECT_ATTENDANCE":
        return
    if command.status not in (
        DeviceCommandStatus.FAILED.value,
        DeviceCommandStatus.DEAD_LETTER.value,
        DeviceCommandStatus.RECONCILIATION_REQUIRED.value,
    ):
        return
    from app.domains.attendance.services.attendance_correction_service import mark_correction_failed_for_command

    mark_correction_failed_for_command(
        db,
        command_uuid=command.command_uuid,
        error_message=error_message,
    )


def _device_service_for_command(db: Session, command: DeviceCommand, settings: Settings) -> DeviceService:
    device = db.execute(select(Device).where(Device.name == command.device_id)).scalar_one_or_none()
    if device is None:
        raise ValueError(
            f"Device '{command.device_id}' not found in registry; "
            "refusing env IP fallback."
        )
    return DeviceService(connection=DeviceConnectionConfig.from_device(device, settings))


def process_command(
    db: Session,
    command: DeviceCommand,
    *,
    settings: Settings | None = None,
    worker_id: str | None = None,
) -> None:
    settings = settings or get_settings()
    _ = worker_id or os.getenv("HOSTNAME") or "unknown-worker"
    if command.status in (DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value):
        now = _utcnow()
        command.status = DeviceCommandStatus.RUNNING.value
        _append_status_history(command, DeviceCommandStatus.RUNNING.value)
        command.started_at = command.started_at or now
        command.heartbeat_at = now
    if not device_policy.DEVICE_WRITES_ENABLED:
        command.status = DeviceCommandStatus.FAILED.value
        command.completed_at = _utcnow()
        command.last_error = "Device writes are disabled by policy."
        _mark_correction_failed_if_needed(db, command, error_message=command.last_error)
        return
    allowed, reason = assert_device_write_allowed(db, device_id=command.device_id)
    if not allowed:
        command.status = DeviceCommandStatus.RECONCILIATION_REQUIRED.value
        command.completed_at = _utcnow()
        command.last_error = reason or "governance policy blocked operation"
        _mark_correction_failed_if_needed(db, command, error_message=command.last_error)
        return
    lock_blocking = (
        float(settings.zk_device_timeout_seconds)
        if command.command_type == "CORRECT_ATTENDANCE"
        else None
    )
    client, lock, lock_key = _acquire_lock(command.device_id, settings, blocking_timeout=lock_blocking)
    if lock is None:
        command.retries += 1
        command.retry_backoff_seconds = 5
        command.status = DeviceCommandStatus.RETRYING.value
        command.next_attempt_at = _utcnow() + timedelta(seconds=5)
        command.last_error = "Device lock contention — another write is in progress. Retry in a few seconds."
        logger.warning(
            "Device lock contention for command %s device=%s key=%s retries=%s",
            command.command_uuid,
            command.device_id,
            lock_key,
            command.retries,
        )
        if command.retries >= settings.command_max_retries:
            command.status = DeviceCommandStatus.DEAD_LETTER.value
            command.completed_at = _utcnow()
            command.last_error = "Device lock contention exceeded retry limit."
            _mark_correction_failed_if_needed(db, command, error_message=command.last_error)
        return

    lock_heartbeat = _LockHeartbeat(
        lock,
        period_seconds=settings.command_heartbeat_seconds,
        extension_seconds=settings.zk_device_timeout_seconds + settings.command_heartbeat_seconds + 10,
    )
    lock_heartbeat.start()
    try:
        try:
            device_service = _device_service_for_command(db, command, settings)
        except ValueError as exc:
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = str(exc)
            _mark_correction_failed_if_needed(db, command, error_message=command.last_error)
            return
        allowlist = DeviceService.safe_command_allowlist()
        if command.command_type not in allowlist:
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = f"Unsafe command type rejected: {command.command_type}"
            _mark_correction_failed_if_needed(db, command, error_message=command.last_error)
            return

        command.heartbeat_at = _utcnow()
        try:
            fingerprint = device_service.detect_firmware_fingerprint()
            firmware_version = str(fingerprint.get("firmware_version") or "unknown")
            command.firmware_profile = firmware_version
        except Exception:  # noqa: BLE001
            logger.debug("firmware fingerprint probe failed for %s", command.device_id)

        payload = command.payload
        if command.command_type == "CORRECT_ATTENDANCE":
            _execute_correct_attendance_command(
                command=command,
                device_service=device_service,
                payload=payload,
            )
            if command.status == DeviceCommandStatus.SUCCESS.value:
                from app.domains.attendance.services.attendance_correction_service import finalize_pending_correction_for_command

                finalize_pending_correction_for_command(db, command.command_uuid)
            else:
                _mark_correction_failed_if_needed(
                    db,
                    command,
                    error_message=command.last_error or "CORRECT_ATTENDANCE command failed.",
                )
            return

        if command.command_type == "DELETE_USER" or command.command_type == "REMOTE_DELETE":
            if command.retries > 0 and _recover_if_delete_already_applied(
                command=command,
                device_service=device_service,
                payload=payload,
            ):
                return

            if settings.command_cooldown_ms > 0:
                time.sleep(settings.command_cooldown_ms / 1000.0)

            user_id = str(payload["user_id"]).strip()
            uid_raw = payload.get("uid")
            uid = int(uid_raw) if uid_raw is not None else None
            already_absent, _ = device_service.verify_user_deleted(user_id=user_id)
            if not already_absent:
                device_service.delete_user(uid=uid, user_id=user_id)

            command.heartbeat_at = _utcnow()
            command.status = DeviceCommandStatus.VERIFYING.value
            verified = _verify_delete_result(
                command=command, device_service=device_service, payload=payload
            )
            if not verified:
                command.status = DeviceCommandStatus.FAILED.value
                command.completed_at = _utcnow()
                command.last_error = "Delete verification failed: user still present on device."
                return

            command.status = DeviceCommandStatus.SUCCESS.value
            command.completed_at = _utcnow()
            command.last_error = None
            return

            command.last_error = None
            return

        if command.command_type == "RESTART":
            device_service.restart_device()
            command.status = DeviceCommandStatus.SUCCESS.value
            command.completed_at = _utcnow()
            command.last_error = None
            return

        if command.command_type == "SYNC_TIME":
            synced_at = device_service.sync_device_time()
            command.verification_details = {"synced_at": synced_at.isoformat()}
            command.status = DeviceCommandStatus.SUCCESS.value
            command.completed_at = _utcnow()
            command.last_error = None
            return

        if command.command_type == "REMOTE_CONFIG":
            config = payload.get("config") or payload
            applied = device_service.apply_remote_config(dict(config))
            command.verification_details = {"applied": applied}
            command.status = DeviceCommandStatus.SUCCESS.value
            command.completed_at = _utcnow()
            command.last_error = None
            return

        if command.command_type == "FIRMWARE_CHECK":
            fingerprint = device_service.detect_firmware_fingerprint()
            command.verification_details = fingerprint
            command.firmware_profile = str(fingerprint.get("firmware_version") or "unknown")
            command.status = DeviceCommandStatus.SUCCESS.value
            command.completed_at = _utcnow()
            command.last_error = None
            return

        if command.command_type == "FORCE_SYNC":
            from app.domains.attendance.services.attendance_service import run_device_sync, run_user_sync

            full_resync = bool(payload.get("full_resync", True))
            users_fetched, users_upserted = run_user_sync(
                db, device=device_service, settings=settings, device_id=command.device_id
            )
            fetched, inserted, placeholders = run_device_sync(
                db,
                device=device_service,
                settings=settings,
                full_resync=full_resync,
                device_id=command.device_id,
            )
            command.verification_details = {
                "users_fetched": users_fetched,
                "users_upserted": users_upserted,
                "fetched": fetched,
                "inserted": inserted,
                "placeholder_employees": placeholders,
            }
            command.status = DeviceCommandStatus.SUCCESS.value
            command.completed_at = _utcnow()
            command.last_error = None
            return

        if command.command_type == "REMOTE_ENROLL":
            enroll_payload = dict(payload)
            enroll_payload.setdefault("name", enroll_payload.get("name") or enroll_payload.get("user_id"))
            payload = enroll_payload

        # UPSERT_USER (default path for remaining allowlisted write commands)
        if command.retries > 0 and _recover_if_already_applied(
            command=command,
            device_service=device_service,
            payload=payload,
        ):
            return

        current_user = _find_current_user_on_device(
            device_service,
            user_id=str(payload.get("user_id") or ""),
        )
        policy_ok, policy_error = _enforce_safe_write_policy(
            settings=settings,
            payload=payload,
            current_on_device=current_user,
        )
        if not policy_ok:
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = policy_error
            return

        if settings.command_cooldown_ms > 0:
            time.sleep(settings.command_cooldown_ms / 1000.0)

        device_service.upsert_user(
            user_id=str(payload["user_id"]),
            name=str(payload["name"]),
            uid=payload.get("uid"),
            privilege=payload.get("privilege"),
            group_id=payload.get("group_id"),
            card=payload.get("card"),
        )
        command.heartbeat_at = _utcnow()
        command.status = DeviceCommandStatus.VERIFYING.value
        verified = _verify_upsert_result(
            command=command, device_service=device_service, payload=payload
        )
        if not verified:
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = "Write verification mismatch after device readback."
            return

        command.status = DeviceCommandStatus.SUCCESS.value
        command.completed_at = _utcnow()
        command.last_error = None
    except Exception as exc:  # noqa: BLE001
        _mark_retry_or_terminal(command, settings=settings, error_message=str(exc))
        _mark_correction_failed_if_needed(
            db,
            command,
            error_message=command.last_error or str(exc),
        )
    finally:
        lock_heartbeat.stop()
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.debug("redis client close failed for device lock")
