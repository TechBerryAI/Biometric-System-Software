"""Celery tasks (device polling, session rebuild)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.services.attendance_service import run_device_sync, run_user_sync
from app.services.device_command_service import claim_pending_commands, process_command
from app.services.device_registry_service import reconcile_device_mappings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="app.workers.tasks.sync_attendance_from_device", bind=True, max_retries=3)
def sync_attendance_from_device(self) -> dict[str, int]:
    """Fetch users + attendance from terminal, then rebuild sessions."""
    db = SessionLocal()
    try:
        users_fetched, users_upserted = run_user_sync(db)
        fetched, inserted, backfilled = run_device_sync(db)
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
    except Exception as exc:  # noqa: BLE001
        logger.exception("Attendance sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.process_device_commands", bind=True, max_retries=0)
def process_device_commands(self) -> dict[str, int]:
    """Drain pending device commands using per-device locks."""
    db = SessionLocal()
    processed = 0
    dead_lettered = 0
    try:
        commands = claim_pending_commands(db, settings=settings)
        for command in commands:
            process_command(db, command, settings=settings)
            processed += 1
            if command.status == DeviceCommandStatus.DEAD_LETTER.value:
                dead_lettered += 1
        db.commit()
        return {"processed": processed, "dead_lettered": dead_lettered}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.reconcile_devices", bind=True, max_retries=1)
def reconcile_devices(self) -> dict[str, int]:
    """Detect device-vs-mapping drift and persist reconciliation events."""
    db = SessionLocal()
    try:
        counts = reconcile_device_mappings(db, settings=settings)
        db.commit()
        return counts
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
                DeviceCommand.status == DeviceCommandStatus.RUNNING.value,
                DeviceCommand.started_at < stale_cutoff,
            )
            .all()
        )
        for command in stale:
            if command.retries >= settings.command_max_retries:
                command.status = DeviceCommandStatus.DEAD_LETTER.value
                command.completed_at = datetime.now(ZoneInfo("UTC"))
                continue
            command.status = DeviceCommandStatus.PENDING.value
            command.next_attempt_at = datetime.now(ZoneInfo("UTC"))
            command.last_error = "Recovered stale RUNNING command"
        db.commit()
        return {"recovered": len(stale)}
    finally:
        db.close()
