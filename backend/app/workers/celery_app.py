"""Celery application and beat schedule with dedicated task queues."""

from __future__ import annotations

from datetime import timedelta

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.workers.beat_schedule import OffsetInterval

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
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
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

# expires on beat messages discards backlog when the worker was down longer than the interval.
# initial_delay staggers the first fire so probe/sync/reconcile do not all hit ZK at once.
_beat_schedule: dict[str, dict[str, object]] = {
    "process-device-commands": {
        "task": "app.workers.tasks.process_device_commands",
        "schedule": OffsetInterval(timedelta(seconds=15), initial_delay=5),
        "options": {"queue": "device_commands", "expires": 20},
    },
    "reconcile-devices": {
        "task": "app.workers.tasks.reconcile_devices",
        "schedule": OffsetInterval(
            timedelta(seconds=settings.reconciliation_interval_seconds),
            initial_delay=90,
        ),
        "options": {
            "queue": "reconciliation",
            "expires": max(60, settings.reconciliation_interval_seconds),
        },
    },
    "recover-stale-commands": {
        "task": "app.workers.tasks.recover_stale_commands",
        "schedule": OffsetInterval(timedelta(seconds=60), initial_delay=30),
        "options": {"queue": "device_commands", "expires": 55},
    },
    "archive-old-attendance": {
        "task": "app.workers.tasks.archive_old_attendance",
        "schedule": OffsetInterval(timedelta(hours=24), initial_delay=120),
        "options": {"queue": "reconciliation", "expires": 3600},
    },
}

if settings.device_auto_sync_enabled:
    _beat_schedule["probe-device-connectivity"] = {
        "task": "app.workers.tasks.probe_device_connectivity",
        "schedule": OffsetInterval(
            timedelta(seconds=settings.device_connectivity_probe_seconds),
            initial_delay=10,
        ),
        "options": {
            "queue": "attendance_sync",
            "expires": max(30, settings.device_connectivity_probe_seconds),
        },
    }
    _beat_schedule["sync-attendance-from-device"] = {
        "task": "app.workers.tasks.sync_attendance_from_device",
        "schedule": OffsetInterval(
            timedelta(seconds=settings.device_poll_interval_seconds),
            initial_delay=25,
        ),
        "options": {
            "queue": "attendance_sync",
            "expires": max(60, settings.device_poll_interval_seconds),
        },
    }

celery_app.conf.beat_schedule = _beat_schedule


@worker_process_init.connect
def _dispose_db_connections_on_fork(**_kwargs: object) -> None:
    """Drop inherited parent connections so each prefork child opens its own pool."""
    from app.core.database import dispose_engines

    dispose_engines()


import app.workers.tasks  # noqa: E402, F401 — register task definitions
