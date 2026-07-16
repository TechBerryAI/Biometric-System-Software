"""Celery application and beat schedule with dedicated task queues."""

from __future__ import annotations

from datetime import timedelta

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

# Dedicated queues for horizontal scaling of workers:
#   device_commands  — write/command drain
#   attendance_sync  — pull sync + connectivity probe
#   reconciliation   — drift detect + stale recovery + archive
#   notifications    — outbound notification delivery
QUEUES = (
    "device_commands",
    "attendance_sync",
    "reconciliation",
    "notifications",
)

celery_app = Celery(
    "attendance",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
)

celery_app.conf.update(
    task_default_queue="attendance_sync",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    enable_utc=True,
    task_routes={
        "app.workers.tasks.process_device_commands": {"queue": "device_commands"},
        "app.workers.tasks.recover_stale_commands": {"queue": "device_commands"},
        "app.workers.tasks.sync_attendance_from_device": {"queue": "attendance_sync"},
        "app.workers.tasks.probe_device_connectivity": {"queue": "attendance_sync"},
        "app.workers.tasks.reconcile_devices": {"queue": "reconciliation"},
        "app.workers.tasks.archive_old_attendance": {"queue": "reconciliation"},
        "app.workers.tasks.dispatch_notification": {"queue": "notifications"},
    },
    task_queues=None,  # declare via worker -Q; routes above select destination
)

_beat_schedule: dict[str, dict[str, object]] = {
    "process-device-commands": {
        "task": "app.workers.tasks.process_device_commands",
        "schedule": timedelta(seconds=15),
        "options": {"queue": "device_commands"},
    },
    "reconcile-devices": {
        "task": "app.workers.tasks.reconcile_devices",
        "schedule": timedelta(seconds=settings.reconciliation_interval_seconds),
        "options": {"queue": "reconciliation"},
    },
    "recover-stale-commands": {
        "task": "app.workers.tasks.recover_stale_commands",
        "schedule": timedelta(seconds=60),
        "options": {"queue": "device_commands"},
    },
    "archive-old-attendance": {
        "task": "app.workers.tasks.archive_old_attendance",
        "schedule": timedelta(hours=24),
        "options": {"queue": "reconciliation"},
    },
}

if settings.device_auto_sync_enabled:
    _beat_schedule["probe-device-connectivity"] = {
        "task": "app.workers.tasks.probe_device_connectivity",
        "schedule": timedelta(seconds=settings.device_connectivity_probe_seconds),
        "options": {"queue": "attendance_sync"},
    }
    _beat_schedule["sync-attendance-from-device"] = {
        "task": "app.workers.tasks.sync_attendance_from_device",
        "schedule": timedelta(seconds=settings.device_poll_interval_seconds),
        "options": {"queue": "attendance_sync"},
    }

celery_app.conf.beat_schedule = _beat_schedule

import app.workers.tasks  # noqa: E402, F401 — register task definitions
