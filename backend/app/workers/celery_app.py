"""Celery application and beat schedule (attendance poll every 2 minutes)."""

from __future__ import annotations

from datetime import timedelta

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "attendance",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
)

celery_app.conf.update(
    task_default_queue="attendance",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "sync-attendance-from-device": {
        "task": "app.workers.tasks.sync_attendance_from_device",
        "schedule": timedelta(seconds=settings.device_poll_interval_seconds),
    },
    "process-device-commands": {
        "task": "app.workers.tasks.process_device_commands",
        "schedule": timedelta(seconds=15),
    },
    "reconcile-devices": {
        "task": "app.workers.tasks.reconcile_devices",
        "schedule": timedelta(seconds=settings.reconciliation_interval_seconds),
    },
    "recover-stale-commands": {
        "task": "app.workers.tasks.recover_stale_commands",
        "schedule": timedelta(seconds=60),
    },
    "process-reconciliation-jobs": {
        "task": "app.workers.tasks.process_reconciliation_jobs",
        "schedule": timedelta(seconds=settings.reconciliation_interval_seconds),
    },
    "capture-device-snapshot": {
        "task": "app.workers.tasks.capture_device_snapshot",
        "schedule": timedelta(seconds=settings.snapshot_interval_seconds),
    },
    "flag-stale-reconciliation-jobs": {
        "task": "app.workers.tasks.flag_stale_reconciliation_jobs",
        "schedule": timedelta(seconds=settings.reconciliation_interval_seconds),
    },
    "aggregate-fleet-health": {
        "task": "app.workers.tasks.aggregate_fleet_health",
        "schedule": timedelta(seconds=settings.reconciliation_interval_seconds),
    },
    "apply-retention-policies": {
        "task": "app.workers.tasks.apply_retention_policies",
        "schedule": timedelta(hours=6),
    },
    "seed-firmware-certifications": {
        "task": "app.workers.tasks.seed_firmware_certifications",
        "schedule": timedelta(hours=1),
    },
}

import app.workers.tasks  # noqa: E402, F401 — register task definitions

