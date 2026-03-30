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
}

import app.workers.tasks  # noqa: E402, F401 — register task definitions

