"""Celery tasks (device polling, session rebuild)."""

from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.services.attendance_service import run_device_sync
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.sync_attendance_from_device", bind=True, max_retries=3)
def sync_attendance_from_device(self) -> dict[str, int]:
    """Fetch attendance from terminal (read-only), insert logs, rebuild sessions."""
    db = SessionLocal()
    try:
        fetched, inserted = run_device_sync(db)
        logger.info("Attendance sync: fetched=%s new_rows=%s", fetched, inserted)
        return {"fetched": fetched, "inserted": inserted}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Attendance sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()
