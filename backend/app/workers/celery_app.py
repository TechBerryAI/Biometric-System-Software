"""Celery application and beat schedule with dedicated task queues."""

from __future__ import annotations

from datetime import timedelta

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging_config import install_log_redaction
from app.workers.beat_schedule import OffsetInterval

install_log_redaction()

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

# Redis lives on another host: keepalives + health checks recover connections a firewall
# silently dropped, and bounded timeouts stop a dead Redis from hanging workers.
_REDIS_TRANSPORT_OPTIONS = {
    "socket_keepalive": True,
    "socket_connect_timeout": 10,
    "socket_timeout": 30,
    "health_check_interval": 25,
    "retry_on_timeout": True,
    # Longest task (manual full pull) is capped at 15 min; redeliver unacked work only after that.
    "visibility_timeout": 3600,
}

celery_app.conf.update(
    task_default_queue="attendance_sync",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.resolved_timezone(),
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    broker_transport_options=_REDIS_TRANSPORT_OPTIONS,
    redis_socket_keepalive=True,
    redis_socket_connect_timeout=10,
    redis_socket_timeout=30,
    redis_retry_on_timeout=True,
    redis_backend_health_check_interval=25,
    result_expires=6 * 3600,
    # A hung device socket must not pin a worker slot forever (manual sync sets its own limits).
    task_soft_time_limit=1500,
    task_time_limit=1800,
    # Recycle children periodically so slow leaks (pyzk sockets, large ORM sessions) cannot build up.
    worker_max_tasks_per_child=200,
    worker_max_memory_per_child=512_000,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    task_routes={
        "app.workers.tasks.process_device_commands": {"queue": "device_commands"},
        "app.workers.tasks.recover_stale_commands": {"queue": "device_commands"},
        "app.workers.tasks.sync_attendance_from_device": {"queue": "attendance_sync"},
        "app.workers.tasks.run_manual_device_sync": {"queue": "attendance_sync"},
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
    from app.core.database import SessionLocal, dispose_engines
    from app.domains.devices.services.device_registry_service import ensure_default_device

    dispose_engines()
    try:
        with SessionLocal() as db:
            device = ensure_default_device(db, settings)
            db.commit()
            if device.timezone:
                celery_app.conf.timezone = device.timezone
    except Exception:  # noqa: BLE001
        pass


import app.workers.tasks  # noqa: E402, F401 — register task definitions
