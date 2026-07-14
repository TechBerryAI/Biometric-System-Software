"""Celery tasks (device polling, session rebuild)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.attendance.services.attendance_service import run_device_sync, run_user_sync
from app.domains.devices.services.device_command_service import claim_pending_commands, device_session_lock, process_command
from app.domains.devices.services.device_service import DeviceService
from app.shared.device_exceptions import DeviceFetchError, DeviceLockContentionError
from app.domains.devices.services.device_registry_service import reconcile_device_mappings, update_device_health
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="app.workers.tasks.sync_attendance_from_device", bind=True, max_retries=3)
def sync_attendance_from_device(self) -> dict[str, int | bool]:
    """Fetch users + attendance from terminal, then rebuild sessions."""
    if not settings.device_auto_sync_enabled:
        logger.info("Attendance sync skipped (DEVICE_AUTO_SYNC_ENABLED=false)")
        return {"skipped": True}
    db = SessionLocal()
    try:
        with device_session_lock(settings.zk_device_id, settings):
            users_fetched, users_upserted = run_user_sync(db, settings=settings)
            fetched, inserted, backfilled = run_device_sync(db, settings=settings)
        update_device_health(db, status="ONLINE", detail="auto_sync_ok", settings=settings)
        db.commit()
        logger.info(
            "Attendance sync: users_fetched=%s users_upserted=%s fetched=%s new_rows=%s placeholder_employees=%s",
            users_fetched,
            users_upserted,
            fetched,
            inserted,
            backfilled,
        )
        return {
            "users_fetched": users_fetched,
            "users_upserted": users_upserted,
            "fetched": fetched,
            "inserted": inserted,
            "placeholder_employees": backfilled,
        }
    except DeviceLockContentionError as exc:
        logger.warning("Attendance sync skipped (device lock busy): %s", exc)
        return {"skipped": True, "reason": "lock_contention"}
    except Exception as exc:  # noqa: BLE001
        update_device_health(db, status="OFFLINE", detail=str(exc), settings=settings)
        db.commit()
        logger.exception("Attendance sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.probe_device_connectivity", bind=True, max_retries=0)
def probe_device_connectivity(self) -> dict[str, str | bool]:
    """TCP + pyzk handshake probe; only runs when auto-sync is enabled."""
    if not settings.device_auto_sync_enabled:
        return {"skipped": True, "reason": "manual_sync_mode"}
    db = SessionLocal()
    try:
        device = DeviceService(settings=settings)
        ok, detail = device.check_connection()
        update_device_health(db, status="ONLINE" if ok else "OFFLINE", detail=detail, settings=settings)
        db.commit()
        return {"online": ok, "detail": detail}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Device connectivity probe failed: %s", exc)
        update_device_health(db, status="OFFLINE", detail=str(exc), settings=settings)
        db.commit()
        return {"online": False, "detail": str(exc)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.process_device_commands", bind=True, max_retries=0)
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


@celery_app.task(name="app.workers.tasks.reconcile_devices", bind=True, max_retries=1)
def reconcile_devices(self) -> dict[str, int]:
    """Detect device-vs-mapping drift."""
    if not settings.device_auto_sync_enabled:
        return {"skipped": True}  # type: ignore[return-value]
    db = SessionLocal()
    try:
        with device_session_lock(settings.zk_device_id, settings):
            counts = reconcile_device_mappings(db, settings=settings)
        db.commit()
        return counts
    except DeviceLockContentionError as exc:
        logger.warning("Device reconciliation skipped (device lock busy): %s", exc)
        return {"skipped": 1}  # type: ignore[return-value]
    except (DeviceFetchError, OSError) as exc:
        update_device_health(db, status="OFFLINE", detail=str(exc), settings=settings)
        db.commit()
        logger.warning("Device reconciliation skipped (device offline): %s", exc)
        return {"offline": 1}  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Device reconciliation failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.recover_stale_commands", bind=True, max_retries=0)
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
