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
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.privileged_account import is_privileged_account
from app.core.redis_keys import with_namespace
from app.models.certified_firmware_profile import CertifiedFirmwareProfile
from app.models.command_execution_history import CommandExecutionHistory
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_firmware_profile import DeviceFirmwareProfile
from app.models.device_runtime_health import DeviceRuntimeHealth
from app.models.device_state_snapshot import DeviceStateSnapshot
from app.models.device_sync_event import DeviceSyncEvent
from app.models.operation_safety_profile import OperationSafetyProfile
from app.models.reconciliation_job import ReconciliationJob
from app.models.user import User
from app.models.verification_result import VerificationResult
from app.services.audit_service import append_audit_log
from app.services.device_service import DeviceService
from app.services.device_exceptions import DeviceLockContentionError
from app.services.system_governance_service import assert_device_write_allowed

logger = logging.getLogger(__name__)

INTERNAL_COMMAND_TYPES = frozenset({"CORRECT_ATTENDANCE"})
INTERNAL_AUDIT_ACTIONS = frozenset({"ATTENDANCE_ADJUST", "GOD_ATTENDANCE_CORRECT"})


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


def _snapshot_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
    settings = get_settings()
    if settings.device_read_only:
        raise RuntimeError("Device write operations are disabled by DEVICE_READ_ONLY mode.")
    allowed, reason = assert_device_write_allowed(db, device_id=device_id)
    if not allowed:
        raise RuntimeError(reason or "Device writes are blocked by governance policy.")
    allowlist = DeviceService.safe_command_allowlist()
    if command_type not in allowlist:
        raise RuntimeError(f"Rejected unsafe command type '{command_type}'.")
    if command_type in INTERNAL_COMMAND_TYPES:
        if not created_by:
            raise RuntimeError("CORRECT_ATTENDANCE requires an authenticated privileged actor.")
        actor = db.execute(select(User).where(User.user_uuid == created_by)).scalar_one_or_none()
        if not is_privileged_account(actor):
            raise RuntimeError("CORRECT_ATTENDANCE is restricted to privileged accounts.")
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
    )
    db.add(command)
    db.flush()
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


def _record_sync_event(
    db: Session,
    *,
    device_id: str,
    event_type: str,
    status: str,
    details: dict[str, Any],
    correlation_id: str | None,
    event_source: str = "worker:device_command",
) -> None:
    db.add(
        DeviceSyncEvent(
            device_id=device_id,
            event_type=event_type,
            event_source=event_source,
            status=status,
            details=details,
            correlation_id=correlation_id,
        )
    )


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


def _record_reconciliation_job(
    db: Session,
    *,
    job_type: str,
    target_entity: str,
    findings: dict[str, Any],
    correlation_id: str | None,
) -> None:
    db.add(
        ReconciliationJob(
            job_type=job_type,
            target_entity=target_entity,
            status="PENDING",
            findings=findings,
            correlation_id=correlation_id,
        )
    )


def _resolve_firmware_profile(
    db: Session,
    *,
    firmware_version: str,
) -> DeviceFirmwareProfile | None:
    return db.execute(
        select(DeviceFirmwareProfile).where(DeviceFirmwareProfile.firmware_version == firmware_version)
    ).scalar_one_or_none()


def _resolve_certified_profile(db: Session, *, firmware_version: str) -> CertifiedFirmwareProfile | None:
    return db.execute(
        select(CertifiedFirmwareProfile).where(CertifiedFirmwareProfile.firmware_version == firmware_version)
    ).scalar_one_or_none()


def _resolve_operation_profile(db: Session, *, operation_type: str) -> OperationSafetyProfile | None:
    return db.execute(
        select(OperationSafetyProfile).where(OperationSafetyProfile.operation_type == operation_type)
    ).scalar_one_or_none()


def _get_or_create_runtime_health(db: Session, *, device_id: str) -> DeviceRuntimeHealth:
    row = db.execute(select(DeviceRuntimeHealth).where(DeviceRuntimeHealth.device_id == device_id)).scalar_one_or_none()
    if row is not None:
        return row
    row = DeviceRuntimeHealth(device_id=device_id)
    db.add(row)
    db.flush()
    return row


def _update_runtime_risk_level(runtime: DeviceRuntimeHealth) -> None:
    score = max(0, runtime.connection_stability_score)
    penalty = (
        runtime.timeout_frequency * 2
        + runtime.reconnect_frequency
        + runtime.protocol_error_rate * 2
        + runtime.verification_failure_rate * 3
        + runtime.drift_score
    )
    effective = max(0, score - penalty)
    if effective < 35:
        runtime.operational_risk_level = "HIGH"
    elif effective < 70:
        runtime.operational_risk_level = "MEDIUM"
    else:
        runtime.operational_risk_level = "LOW"


def _apply_device_mode_transitions(
    db: Session,
    *,
    device_id: str,
    runtime: DeviceRuntimeHealth,
    reason: str | None = None,
) -> None:
    device = db.execute(select(Device).where(Device.name == device_id)).scalar_one_or_none()
    if device is None:
        return
    if runtime.operational_risk_level == "HIGH":
        device.mode = "QUARANTINED"
        if reason:
            device.quarantine_reason = reason[:1000]
    elif runtime.operational_risk_level == "MEDIUM":
        if device.mode not in {"QUARANTINED", "OFFLINE"}:
            device.mode = "DEGRADED"
    else:
        if device.mode in {"DEGRADED"}:
            device.mode = "NORMAL"


def _record_snapshot(
    db: Session,
    *,
    device_service: DeviceService,
    device_id: str,
    snapshot_type: str,
    firmware_version: str | None,
) -> DeviceStateSnapshot:
    users = device_service.fetch_users()
    metadata = {
        "users": [
            {
                "user_id": user.user_id,
                "name": user.name,
                "uid": user.uid,
                "privilege": user.privilege,
                "group_id": user.group_id,
                "card": user.card,
            }
            for user in sorted(users, key=lambda u: (u.user_id, u.uid))
        ]
    }
    row = DeviceStateSnapshot(
        device_id=device_id,
        snapshot_type=snapshot_type,
        snapshot_hash=_snapshot_hash(metadata),
        user_count=len(users),
        user_metadata=metadata,
        firmware_version=firmware_version,
    )
    db.add(row)
    return row


def _start_execution_attempt(db: Session, *, command: DeviceCommand, worker_id: str) -> CommandExecutionHistory:
    latest_attempt = db.execute(
        select(func.max(CommandExecutionHistory.execution_attempt)).where(CommandExecutionHistory.command_id == command.id)
    ).scalar_one()
    base_attempt = command.retries + 1
    attempt = max(base_attempt, (latest_attempt or 0) + 1)
    row = CommandExecutionHistory(
        command_id=command.id,
        execution_attempt=attempt,
        execution_hash=_execution_hash(command, attempt),
        worker_id=worker_id,
        final_status="RUNNING",
    )
    db.add(row)
    db.flush()
    return row


def _finish_execution_attempt(
    row: CommandExecutionHistory,
    *,
    final_status: str,
    verification_result: str | None = None,
) -> None:
    row.final_status = final_status
    row.verification_result = verification_result
    row.completed_at = _utcnow()


def _recover_if_already_applied(
    db: Session,
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
    lookback: int,
) -> bool:
    attempts = list(
        db.execute(
            select(CommandExecutionHistory)
            .where(CommandExecutionHistory.command_id == command.id)
            .order_by(CommandExecutionHistory.started_at.desc())
            .limit(lookback)
        ).scalars().all()
    )
    if not attempts:
        return False
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
    db.add(
        VerificationResult(
            command_id=command.id,
            verification_status="SUCCESS",
            expected_state=details.get("expected_state") or {},
            actual_state=details.get("actual_state"),
            mismatch_details={"replay_recovery": True},
        )
    )
    return True


def _enforce_safe_write_policy(
    *,
    settings: Settings,
    payload: dict[str, Any],
    current_on_device: dict[str, Any] | None,
    firmware_profile: DeviceFirmwareProfile | None,
) -> tuple[bool, str | None]:
    override = bool(payload.get("admin_override"))
    if override and not settings.allow_device_admin_override:
        return False, "admin override is disabled by policy"

    def _changed(field: str) -> bool:
        if current_on_device is None:
            return False
        proposed = payload.get(field)
        if proposed is None:
            return False
        return str(proposed).strip() != str(current_on_device.get(field) or "").strip()

    if _changed("uid"):
        if not settings.allow_device_uid_rewrite and not override:
            return False, "uid rewrite blocked by safety policy"
        if firmware_profile is not None and not firmware_profile.supports_uid_update:
            return False, "firmware profile blocks uid rewrite"
    if _changed("privilege"):
        if not settings.allow_device_privilege_update and not override:
            return False, "privilege rewrite blocked by safety policy"
    if _changed("card"):
        if not settings.allow_device_card_rewrite and not override:
            return False, "card rewrite blocked by safety policy"
        if firmware_profile is not None and not firmware_profile.supports_card_update:
            return False, "firmware profile blocks card rewrite"
    if _changed("name") and firmware_profile is not None and not firmware_profile.supports_name_update:
        return False, "firmware profile blocks name update"
    return True, None

def _verify_upsert_result(
    db: Session,
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
    db.add(
        VerificationResult(
            command_id=command.id,
            verification_status=command.verification_status,
            expected_state=details.get("expected_state") or {},
            actual_state=details.get("actual_state"),
            mismatch_details=details.get("mismatch_details"),
        )
    )
    return ok, details


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _execute_correct_attendance_command(
    db: Session,
    *,
    command: DeviceCommand,
    device_service: DeviceService,
    payload: dict[str, Any],
    execution_row: CommandExecutionHistory,
    runtime_health: DeviceRuntimeHealth,
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
    _finish_execution_attempt(execution_row, final_status="SUCCESS", verification_result="SUCCESS")
    runtime_health.connection_stability_score = min(100, runtime_health.connection_stability_score + 1)
    _update_runtime_risk_level(runtime_health)
    _apply_device_mode_transitions(db, device_id=command.device_id, runtime=runtime_health)
    _record_sync_event(
        db,
        device_id=command.device_id,
        event_type="COMMAND_EXECUTED",
        status="SUCCESS",
        details={"command_uuid": command.command_uuid, "command_type": command.command_type},
        correlation_id=command.correlation_id,
    )


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


def process_command(
    db: Session,
    command: DeviceCommand,
    *,
    settings: Settings | None = None,
    worker_id: str | None = None,
) -> None:
    settings = settings or get_settings()
    worker_id = worker_id or os.getenv("HOSTNAME") or "unknown-worker"
    runtime_health = _get_or_create_runtime_health(db, device_id=command.device_id)
    if command.status in (DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value):
        now = _utcnow()
        command.status = DeviceCommandStatus.RUNNING.value
        command.started_at = command.started_at or now
        command.heartbeat_at = now
    if settings.device_read_only:
        append_audit_log(
            db,
            actor_user_uuid=command.initiated_by,
            action_type="DEVICE_COMMAND_REJECTED_READ_ONLY",
            entity_type="device_command",
            entity_id=command.command_uuid,
            new_state={"command_type": command.command_type, "device_id": command.device_id},
            request_id=command.correlation_id,
        )
        command.status = DeviceCommandStatus.FAILED.value
        command.completed_at = _utcnow()
        command.last_error = "DEVICE_READ_ONLY mode is enabled."
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="COMMAND_REJECTED",
            status="READ_ONLY",
            details={"command_uuid": command.command_uuid, "command_type": command.command_type},
            correlation_id=command.correlation_id,
        )
        runtime_health.connection_stability_score = max(0, runtime_health.connection_stability_score - 5)
        _update_runtime_risk_level(runtime_health)
        _apply_device_mode_transitions(db, device_id=command.device_id, runtime=runtime_health, reason=command.last_error)
        return
    allowed, reason = assert_device_write_allowed(db, device_id=command.device_id)
    if not allowed:
        command.status = DeviceCommandStatus.RECONCILIATION_REQUIRED.value
        command.completed_at = _utcnow()
        command.last_error = reason or "governance policy blocked operation"
        runtime_health.connection_stability_score = max(0, runtime_health.connection_stability_score - 2)
        _update_runtime_risk_level(runtime_health)
        _apply_device_mode_transitions(db, device_id=command.device_id, runtime=runtime_health, reason=command.last_error)
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="GOVERNANCE_BLOCK",
            status="BLOCKED",
            details={"command_uuid": command.command_uuid, "reason": command.last_error},
            correlation_id=command.correlation_id,
        )
        return
    client, lock, lock_key = _acquire_lock(command.device_id, settings)
    if lock is None:
        command.retries += 1
        command.retry_backoff_seconds = 5
        command.status = DeviceCommandStatus.RETRYING.value
        command.next_attempt_at = _utcnow() + timedelta(seconds=5)
        command.last_error = "Device lock contention — another write is in progress. Retry in a few seconds."
        runtime_health.reconnect_frequency += 1
        runtime_health.connection_stability_score = max(0, runtime_health.connection_stability_score - 1)
        _update_runtime_risk_level(runtime_health)
        _apply_device_mode_transitions(db, device_id=command.device_id, runtime=runtime_health, reason=command.last_error)
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="LOCK_CONTENTION",
            status="RETRYING",
            details={"command_uuid": command.command_uuid, "lock_key": lock_key, "retries": command.retries},
            correlation_id=command.correlation_id,
        )
        if command.retries >= settings.command_max_retries:
            command.status = DeviceCommandStatus.DEAD_LETTER.value
            command.completed_at = _utcnow()
            command.last_error = "Device lock contention exceeded retry limit."
        return
    device_service = DeviceService(settings=settings)
    execution_row = _start_execution_attempt(db, command=command, worker_id=worker_id)
    lock_heartbeat = _LockHeartbeat(
        lock,
        period_seconds=settings.command_heartbeat_seconds,
        extension_seconds=settings.zk_device_timeout_seconds + settings.command_heartbeat_seconds + 10,
    )
    lock_heartbeat.start()
    operation_profile: OperationSafetyProfile | None = None
    try:
        allowlist = DeviceService.safe_command_allowlist()
        if command.command_type not in allowlist:
            append_audit_log(
                db,
                actor_user_uuid=command.initiated_by,
                action_type="DEVICE_COMMAND_REJECTED_UNSAFE",
                entity_type="device_command",
                entity_id=command.command_uuid,
                new_state={"command_type": command.command_type, "device_id": command.device_id},
                request_id=command.correlation_id,
            )
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = f"Unsafe command type rejected: {command.command_type}"
            _record_sync_event(
                db,
                device_id=command.device_id,
                event_type="DANGEROUS_COMMAND_REJECTED",
                status="REJECTED",
                details={"command_uuid": command.command_uuid, "command_type": command.command_type},
                correlation_id=command.correlation_id,
            )
            _finish_execution_attempt(execution_row, final_status="FORBIDDEN")
            return

        command.heartbeat_at = _utcnow()
        fingerprint = device_service.detect_firmware_fingerprint()
        firmware_version = str(fingerprint.get("firmware_version") or "unknown")
        command.firmware_profile = firmware_version
        profile = _resolve_firmware_profile(db, firmware_version=firmware_version)
        certified = _resolve_certified_profile(db, firmware_version=firmware_version)
        operation_profile = _resolve_operation_profile(db, operation_type=command.command_type)
        if certified is None or certified.certification_status in {"UNCERTIFIED", "UNSTABLE"}:
            if command.command_type != "CORRECT_ATTENDANCE":
                command.status = DeviceCommandStatus.RECONCILIATION_REQUIRED.value
                command.completed_at = _utcnow()
                command.last_error = f"Firmware '{firmware_version}' is not certified for production writes."
                runtime_health.protocol_error_rate += 1
                runtime_health.connection_stability_score = max(0, runtime_health.connection_stability_score - 8)
                _update_runtime_risk_level(runtime_health)
                _apply_device_mode_transitions(
                    db,
                    device_id=command.device_id,
                    runtime=runtime_health,
                    reason="uncertified firmware auto-restricted",
                )
                _record_reconciliation_job(
                    db,
                    job_type="FIRMWARE_CERTIFICATION_REQUIRED",
                    target_entity=f"device:{command.device_id}",
                    findings={
                        "command_uuid": command.command_uuid,
                        "firmware_version": firmware_version,
                        "certification_status": certified.certification_status if certified else "UNKNOWN",
                    },
                    correlation_id=command.correlation_id,
                )
                device_row = db.execute(select(Device).where(Device.name == command.device_id)).scalar_one_or_none()
                if device_row is not None:
                    device_row.mode = "READ_ONLY"
                    device_row.quarantine_reason = f"uncertified firmware: {firmware_version}"
                _finish_execution_attempt(execution_row, final_status="FIRMWARE_RESTRICTED")
                return
        if operation_profile is not None and operation_profile.risk_level == "FORBIDDEN":
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = f"Operation '{command.command_type}' is classified FORBIDDEN."
            _finish_execution_attempt(execution_row, final_status="FORBIDDEN")
            _record_sync_event(
                db,
                device_id=command.device_id,
                event_type="OPERATION_FORBIDDEN",
                status="REJECTED",
                details={"command_uuid": command.command_uuid, "operation": command.command_type},
                correlation_id=command.correlation_id,
            )
            return
        if profile is not None and not profile.supports_user_write and command.command_type != "CORRECT_ATTENDANCE":
            command.status = DeviceCommandStatus.RECONCILIATION_REQUIRED.value
            command.completed_at = _utcnow()
            command.last_error = f"Firmware profile '{firmware_version}' disallows user write."
            _record_reconciliation_job(
                db,
                job_type="FIRMWARE_CAPABILITY_BLOCK",
                target_entity=f"device:{command.device_id}",
                findings={
                    "command_uuid": command.command_uuid,
                    "firmware_version": firmware_version,
                    "reason": "supports_user_write=false",
                },
                correlation_id=command.correlation_id,
            )
            _finish_execution_attempt(execution_row, final_status="RECONCILIATION_REQUIRED")
            return

        payload = command.payload
        if command.command_type == "CORRECT_ATTENDANCE":
            _execute_correct_attendance_command(
                db,
                command=command,
                device_service=device_service,
                payload=payload,
                execution_row=execution_row,
                runtime_health=runtime_health,
            )
            if command.status == DeviceCommandStatus.SUCCESS.value:
                from app.services.attendance_correction_service import finalize_pending_correction_for_command

                finalize_pending_correction_for_command(db, command.command_uuid)
            elif command.status in (
                DeviceCommandStatus.FAILED.value,
                DeviceCommandStatus.DEAD_LETTER.value,
                DeviceCommandStatus.RECONCILIATION_REQUIRED.value,
            ):
                from app.services.attendance_correction_service import mark_correction_failed_for_command

                mark_correction_failed_for_command(
                    db,
                    command_uuid=command.command_uuid,
                    error_message=command.last_error or "CORRECT_ATTENDANCE command failed.",
                )
            return
        if command.retries > 0:
            recovered = _recover_if_already_applied(
                db,
                command=command,
                device_service=device_service,
                payload=payload,
                lookback=settings.command_max_recover_verification_lookback,
            )
            if recovered:
                _finish_execution_attempt(execution_row, final_status="RECOVERED_SUCCESS", verification_result="SUCCESS")
                _record_sync_event(
                    db,
                    device_id=command.device_id,
                    event_type="COMMAND_RECOVERED_FROM_REPLAY_CHECK",
                    status="SUCCESS",
                    details={"command_uuid": command.command_uuid, "retries": command.retries},
                    correlation_id=command.correlation_id,
                )
                return

        before_snapshot = _record_snapshot(
            db,
            device_service=device_service,
            device_id=command.device_id,
            snapshot_type="PRE_WRITE",
            firmware_version=firmware_version,
        )
        current_user = None
        users = before_snapshot.user_metadata.get("users", [])
        for user in users:
            if str(user.get("user_id") or "").strip() == str(payload.get("user_id") or "").strip():
                current_user = user
                break
        policy_ok, policy_error = _enforce_safe_write_policy(
            settings=settings,
            payload=payload,
            current_on_device=current_user,
            firmware_profile=profile,
        )
        if not policy_ok:
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = policy_error
            _finish_execution_attempt(execution_row, final_status="POLICY_BLOCKED")
            _record_sync_event(
                db,
                device_id=command.device_id,
                event_type="WRITE_POLICY_BLOCKED",
                status="REJECTED",
                details={"command_uuid": command.command_uuid, "reason": policy_error},
                correlation_id=command.correlation_id,
            )
            return

        if profile is not None and profile.write_delay_ms > 0:
            time.sleep(profile.write_delay_ms / 1000.0)
        elif settings.command_cooldown_ms > 0:
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
        _record_snapshot(
            db,
            device_service=device_service,
            device_id=command.device_id,
            snapshot_type="POST_WRITE",
            firmware_version=firmware_version,
        )

        command.status = DeviceCommandStatus.VERIFYING.value
        command.heartbeat_at = _utcnow()
        verified = _verify_upsert_result(db, command=command, device_service=device_service, payload=payload)
        if not verified:
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = "Write verification mismatch after device readback."
            _record_reconciliation_job(
                db,
                job_type="WRITE_VERIFICATION",
                target_entity=f"device:{command.device_id}",
                findings={
                    "command_uuid": command.command_uuid,
                    "verification": command.verification_details,
                },
                correlation_id=command.correlation_id,
            )
            _record_sync_event(
                db,
                device_id=command.device_id,
                event_type="COMMAND_VERIFICATION_FAILED",
                status="FAILED",
                details={
                    "command_uuid": command.command_uuid,
                    "command_type": command.command_type,
                    "verification_status": command.verification_status,
                },
                correlation_id=command.correlation_id,
            )
            _finish_execution_attempt(execution_row, final_status="VERIFICATION_FAILED", verification_result="FAILED")
            runtime_health.verification_failure_rate += 1
            runtime_health.connection_stability_score = max(0, runtime_health.connection_stability_score - 10)
            _update_runtime_risk_level(runtime_health)
            _apply_device_mode_transitions(
                db,
                device_id=command.device_id,
                runtime=runtime_health,
                reason="verification failure spike",
            )
            return

        if operation_profile is not None and operation_profile.requires_manual_review:
            command.status = DeviceCommandStatus.RECONCILIATION_REQUIRED.value
            command.completed_at = _utcnow()
            command.last_error = "Operation requires manual review per safety profile."
            _finish_execution_attempt(execution_row, final_status="REVIEW_REQUIRED", verification_result="SUCCESS")
            _record_reconciliation_job(
                db,
                job_type="MANUAL_REVIEW_REQUIRED",
                target_entity=f"device:{command.device_id}",
                findings={"command_uuid": command.command_uuid, "operation": command.command_type},
                correlation_id=command.correlation_id,
            )
            return

        command.status = DeviceCommandStatus.SUCCESS.value
        command.completed_at = _utcnow()
        command.last_error = None
        _finish_execution_attempt(execution_row, final_status="SUCCESS", verification_result=command.verification_status)
        runtime_health.connection_stability_score = min(100, runtime_health.connection_stability_score + 1)
        runtime_health.verification_failure_rate = max(0, runtime_health.verification_failure_rate - 1)
        _update_runtime_risk_level(runtime_health)
        _apply_device_mode_transitions(db, device_id=command.device_id, runtime=runtime_health)
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="COMMAND_EXECUTED",
            status="SUCCESS",
            details={"command_uuid": command.command_uuid, "command_type": command.command_type},
            correlation_id=command.correlation_id,
        )
    except Exception as exc:  # noqa: BLE001
        _mark_retry_or_terminal(command, settings=settings, error_message=str(exc))
        if operation_profile is not None and not operation_profile.retry_safe:
            command.status = DeviceCommandStatus.DEAD_LETTER.value
            command.completed_at = _utcnow()
        _finish_execution_attempt(execution_row, final_status=command.status, verification_result=command.verification_status)
        runtime_health.timeout_frequency += 1
        runtime_health.reconnect_frequency += 1
        runtime_health.connection_stability_score = max(0, runtime_health.connection_stability_score - 6)
        _update_runtime_risk_level(runtime_health)
        _apply_device_mode_transitions(db, device_id=command.device_id, runtime=runtime_health, reason=command.last_error)
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="COMMAND_FAILED",
            status="FAILED",
            details={"command_uuid": command.command_uuid, "error": command.last_error, "retries": command.retries},
            correlation_id=command.correlation_id,
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
