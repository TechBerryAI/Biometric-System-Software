"""Unit tests for celery queue routing."""

from __future__ import annotations

import pytest

from app.workers import celery_app as celery_mod


@pytest.mark.testid("BE-UNIT-CELERY-001")
def test_celery_task_routes_configured() -> None:
    routes = celery_mod.celery_app.conf.task_routes
    assert routes["app.workers.tasks.process_device_commands"]["queue"] == "device_commands"
    assert routes["app.workers.tasks.sync_attendance_from_device"]["queue"] == "attendance_sync"
    assert routes["app.workers.tasks.run_manual_device_sync"]["queue"] == "attendance_sync"
    assert routes["app.workers.tasks.reconcile_devices"]["queue"] == "reconciliation"
    assert routes["app.workers.tasks.dispatch_notification"]["queue"] == "notifications"
    assert routes["app.workers.tasks.archive_old_attendance"]["queue"] == "reconciliation"


@pytest.mark.testid("BE-UNIT-CELERY-002")
def test_dedicated_queues_declared() -> None:
    assert "device_commands" in celery_mod.QUEUES
    assert "notifications" in celery_mod.QUEUES
