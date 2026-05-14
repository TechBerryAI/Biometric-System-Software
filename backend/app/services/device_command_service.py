"""Queueing and execution helpers for safe device commands."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from redis import Redis
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_sync_event import DeviceSyncEvent
from app.services.device_service import DeviceService


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _idempotency_key(device_id: str, command_type: str, payload: dict[str, Any]) -> str:
    canonical = f"{device_id}:{command_type}:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def enqueue_device_command(
    db: Session,
    *,
    device_id: str,
    command_type: str,
    payload: dict[str, Any],
    correlation_id: str | None,
    created_by: str | None,
) -> DeviceCommand:
    key = _idempotency_key(device_id, command_type, payload)
    existing = db.execute(select(DeviceCommand).where(DeviceCommand.idempotency_key == key)).scalar_one_or_none()
    if existing is not None:
        return existing
    command = DeviceCommand(
        device_id=device_id,
        command_type=command_type,
        payload=payload,
        status=DeviceCommandStatus.PENDING.value,
        correlation_id=correlation_id,
        created_by=created_by,
        idempotency_key=key,
        next_attempt_at=_utcnow(),
    )
    db.add(command)
    db.flush()
    return command


def claim_pending_commands(db: Session, *, settings: Settings | None = None) -> list[DeviceCommand]:
    settings = settings or get_settings()
    now = _utcnow()
    query = (
        select(DeviceCommand)
        .where(
            DeviceCommand.status == DeviceCommandStatus.PENDING.value,
            or_(DeviceCommand.next_attempt_at.is_(None), DeviceCommand.next_attempt_at <= now),
        )
        .order_by(DeviceCommand.created_at.asc())
        .limit(settings.command_queue_batch_size)
        .with_for_update(skip_locked=True)
    )
    commands = list(db.execute(query).scalars().all())
    for command in commands:
        command.status = DeviceCommandStatus.RUNNING.value
        command.started_at = now
    return commands


def _record_sync_event(
    db: Session,
    *,
    device_id: str,
    event_type: str,
    status: str,
    details: dict[str, Any],
    correlation_id: str | None,
) -> None:
    db.add(
        DeviceSyncEvent(
            device_id=device_id,
            event_type=event_type,
            status=status,
            details=details,
            correlation_id=correlation_id,
        )
    )


def _acquire_lock(device_id: str, settings: Settings) -> tuple[Redis | None, Any]:
    try:
        client = Redis.from_url(str(settings.redis_url), socket_timeout=2, socket_connect_timeout=2)
        lock_key = with_namespace(settings.redis_namespace, f"device:lock:{device_id}")
        lock = client.lock(lock_key, timeout=settings.zk_device_timeout_seconds + 10, blocking_timeout=1)
        if lock.acquire(blocking=False):
            return client, lock
    except Exception:  # noqa: BLE001
        return None, None
    return None, None


def process_command(db: Session, command: DeviceCommand, *, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    client, lock = _acquire_lock(command.device_id, settings)
    if lock is None:
        command.status = DeviceCommandStatus.PENDING.value
        return
    try:
        if command.command_type != "UPSERT_USER":
            raise RuntimeError(f"Unsupported command type: {command.command_type}")
        payload = command.payload
        DeviceService(settings=settings).upsert_user(
            user_id=str(payload["user_id"]),
            name=str(payload["name"]),
            uid=payload.get("uid"),
            privilege=payload.get("privilege"),
            group_id=payload.get("group_id"),
            card=payload.get("card"),
        )
        command.status = DeviceCommandStatus.SUCCESS.value
        command.completed_at = _utcnow()
        command.last_error = None
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="COMMAND_EXECUTED",
            status="SUCCESS",
            details={"command_uuid": command.command_uuid, "command_type": command.command_type},
            correlation_id=command.correlation_id,
        )
    except Exception as exc:  # noqa: BLE001
        command.retries += 1
        command.last_error = str(exc)[:2000]
        if command.retries >= settings.command_max_retries:
            command.status = DeviceCommandStatus.DEAD_LETTER.value
            command.completed_at = _utcnow()
        else:
            delay = settings.command_retry_base_seconds * (2 ** (command.retries - 1))
            command.status = DeviceCommandStatus.PENDING.value
            command.next_attempt_at = _utcnow() + timedelta(seconds=delay)
        _record_sync_event(
            db,
            device_id=command.device_id,
            event_type="COMMAND_FAILED",
            status="FAILED",
            details={"command_uuid": command.command_uuid, "error": command.last_error, "retries": command.retries},
            correlation_id=command.correlation_id,
        )
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001
            pass
