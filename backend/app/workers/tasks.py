"""Celery tasks (device polling, session rebuild, archive, notifications)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.domains.attendance.services.archive_service import archive_old_attendance as archive_old_attendance_rows
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.devices.services.device_command_service import claim_pending_commands, process_command
from app.domains.devices.services.device_registry_service import ensure_default_device, reconcile_all_devices
from app.domains.devices.services.branch_sync_service import sync_branch
from app.domains.devices.services.heartbeat_service import probe_all_devices
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(
    name="app.workers.tasks.sync_attendance_from_device",
    bind=True,
    max_retries=3,
    queue="attendance_sync",
)
def sync_attendance_from_device(self) -> dict[str, int | bool | list]:
    """Fetch users + attendance from all pull-mode fleet devices."""
    if not settings.device_auto_sync_enabled:
        logger.info("Attendance sync skipped (DEVICE_AUTO_SYNC_ENABLED=false)")
        return {"skipped": True}
    db = SessionLocal()
    try:
        ensure_default_device(db, settings)
        db.commit()
        results = sync_branch(db, branch_id=None, full_resync=True, settings=settings)
        db.commit()
        total_inserted = sum(int(r.get("inserted", 0)) for r in results if isinstance(r.get("inserted"), int))
        logger.info("Fleet attendance sync completed: devices=%s total_inserted=%s", len(results), total_inserted)
        return {"devices": len(results), "total_inserted": total_inserted, "results": results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fleet attendance sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.probe_device_connectivity",
    bind=True,
    max_retries=0,
    queue="attendance_sync",
)
def probe_device_connectivity(self) -> dict[str, object]:
    """TCP + pyzk handshake probe for all pull-mode fleet devices."""
    if not settings.device_auto_sync_enabled:
        return {"skipped": True, "reason": "manual_sync_mode"}
    db = SessionLocal()
    try:
        ensure_default_device(db, settings)
        db.commit()
        results = probe_all_devices(db, settings=settings)
        db.commit()
        online = sum(1 for r in results if r.get("online"))
        return {"probed": len(results), "online": online, "results": results}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fleet connectivity probe failed: %s", exc)
        return {"online": False, "detail": str(exc)}
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.process_device_commands",
    bind=True,
    max_retries=0,
    queue="device_commands",
)
def process_device_commands(self) -> dict[str, int]:
    """Drain pending device commands using per-device locks."""
    db = SessionLocal()
    processed = 0
    dead_lettered = 0
    verification_failed = 0
    worker_id = getattr(self.request, "hostname", None) or os.getenv("HOSTNAME") or "celery-worker"
    try:
        commands = claim_pending_commands(db, settings=settings)
        db.commit()
        for command in commands:
            process_command(db, command, settings=settings, worker_id=worker_id)
            processed += 1
            if command.status == DeviceCommandStatus.DEAD_LETTER.value:
                dead_lettered += 1
            if command.verification_status == "FAILED":
                verification_failed += 1
            db.commit()
        return {"processed": processed, "dead_lettered": dead_lettered, "verification_failed": verification_failed}
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.reconcile_devices",
    bind=True,
    max_retries=1,
    queue="reconciliation",
)
def reconcile_devices(self) -> dict[str, int | list]:
    """Detect device-vs-mapping drift across fleet."""
    if not settings.device_auto_sync_enabled:
        return {"skipped": True}  # type: ignore[return-value]
    db = SessionLocal()
    try:
        ensure_default_device(db, settings)
        db.commit()
        results = reconcile_all_devices(db, settings=settings)
        db.commit()
        total_drift = sum(
            int(r.get("missing_on_device", 0)) + int(r.get("missing_mapping", 0))
            for r in results
            if "error" not in r
        )
        return {"devices": len(results), "total_drift": total_drift, "results": results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fleet reconciliation failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.recover_stale_commands",
    bind=True,
    max_retries=0,
    queue="device_commands",
)
def recover_stale_commands(self) -> dict[str, int]:
    """Move stale RUNNING commands back to PENDING for reprocessing."""
    db = SessionLocal()
    try:
        stale_cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=settings.command_stale_minutes)
        stale = (
            db.query(DeviceCommand)
            .filter(
                DeviceCommand.status.in_([DeviceCommandStatus.RUNNING.value, DeviceCommandStatus.VERIFYING.value]),
                or_(
                    DeviceCommand.heartbeat_at < stale_cutoff,
                    and_(DeviceCommand.heartbeat_at.is_(None), DeviceCommand.started_at < stale_cutoff),
                ),
            )
            .all()
        )
        for command in stale:
            if command.retries >= settings.command_max_retries:
                command.status = DeviceCommandStatus.DEAD_LETTER.value
                command.completed_at = datetime.now(ZoneInfo("UTC"))
                continue
            command.status = DeviceCommandStatus.RETRYING.value
            command.next_attempt_at = datetime.now(ZoneInfo("UTC"))
            command.last_error = "Recovered stale RUNNING command"
            command.retry_backoff_seconds = 0
        db.commit()
        return {"recovered": len(stale)}
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.archive_old_attendance",
    bind=True,
    max_retries=1,
    queue="reconciliation",
)
def archive_old_attendance(self) -> dict[str, object]:
    """Record / optionally delete attendance rows past retention."""
    db = SessionLocal()
    try:
        result = archive_old_attendance_rows(db, settings=settings)
        db.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Attendance archive failed: %s", exc)
        raise self.retry(exc=exc, countdown=300) from exc
    finally:
        db.close()


@celery_app.task(
    name="app.workers.tasks.dispatch_notification",
    bind=True,
    max_retries=3,
    queue="notifications",
)
def dispatch_notification(self, channel: str, payload: dict) -> dict[str, object]:
    """Deliver a notification via configured channel adapters."""
    try:
        from app.domains.notifications.channels.base import NotificationPayload
        from app.domains.notifications.notification_service import NotificationService

        service = NotificationService()
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        notif = NotificationPayload(
            recipient=str(payload.get("recipient", "")),
            subject=payload.get("subject"),
            body=str(payload.get("body", "")),
            metadata={str(k): str(v) for k, v in meta.items()},
        )
        ok = service.send(channel, notif)
        return {"ok": ok, "channel": channel}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Notification dispatch failed channel=%s: %s", channel, exc)
        raise self.retry(exc=exc, countdown=30) from exc
