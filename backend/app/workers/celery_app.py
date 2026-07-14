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

_beat_schedule: dict[str, dict[str, object]] = {
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
}

if settings.device_auto_sync_enabled:
    _beat_schedule["probe-device-connectivity"] = {
        "task": "app.workers.tasks.probe_device_connectivity",
        "schedule": timedelta(seconds=settings.device_connectivity_probe_seconds),
    }
    _beat_schedule["sync-attendance-from-device"] = {
        "task": "app.workers.tasks.sync_attendance_from_device",
        "schedule": timedelta(seconds=settings.device_poll_interval_seconds),
    }

celery_app.conf.beat_schedule = _beat_schedule

import app.workers.tasks  # noqa: E402, F401 — register task definitions
