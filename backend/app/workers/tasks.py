"""Celery tasks (device polling, session rebuild)."""

from __future__ import annotations

import logging
import os
from hashlib import sha256
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.certified_firmware_profile import CertifiedFirmwareProfile
from app.models.command_execution_history import CommandExecutionHistory
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_runtime_health import DeviceRuntimeHealth
from app.models.device_state_snapshot import DeviceStateSnapshot
from app.models.fleet_health_metric import FleetHealthMetric
from app.models.reconciliation_job import ReconciliationJob
from app.services.attendance_service import run_device_sync, run_user_sync
from app.services.device_command_service import claim_pending_commands, process_command
from app.services.device_service import DeviceService
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


@celery_app.task(name="app.workers.tasks.process_reconciliation_jobs", bind=True, max_retries=0)
def process_reconciliation_jobs(self) -> dict[str, int]:
    """Mark pending reconciliation jobs as reviewed until auto-repair actions are added."""
    db = SessionLocal()
    try:
        jobs = (
            db.query(ReconciliationJob)
            .filter(ReconciliationJob.status == "PENDING")
            .order_by(ReconciliationJob.created_at.asc())
            .limit(100)
            .all()
        )
        for job in jobs:
            job.status = "REVIEW_REQUIRED"
        db.commit()
        return {"updated": len(jobs)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.capture_device_snapshot", bind=True, max_retries=1)
def capture_device_snapshot(self) -> dict[str, int | str]:
    """Capture periodic read-only snapshot for drift forensics."""
    db = SessionLocal()
    try:
        service = DeviceService(settings=settings)
        firmware = service.detect_firmware_fingerprint().get("firmware_version")
        users = service.fetch_users()
        metadata = {
            "users": [
                {
                    "user_id": user.user_id,
                    "name": user.name,
                    "uid": user.uid,
                    "privilege": user.privilege,
                    "group_id": user.group_id,
                    "card": user.card,
                }
                for user in sorted(users, key=lambda u: (u.user_id, u.uid))
            ]
        }
        hash_value = sha256(str(metadata).encode("utf-8")).hexdigest()
        row = DeviceStateSnapshot(
            device_id=settings.zk_device_id,
            snapshot_type="PERIODIC",
            snapshot_hash=hash_value,
            user_count=len(users),
            user_metadata=metadata,
            firmware_version=str(firmware or "unknown"),
        )
        db.add(row)
        db.commit()
        return {"user_count": len(users), "snapshot_hash": hash_value}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Device snapshot capture failed: %s", exc)
        raise self.retry(exc=exc, countdown=60) from exc
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.flag_stale_reconciliation_jobs", bind=True, max_retries=0)
def flag_stale_reconciliation_jobs(self) -> dict[str, int]:
    """Promote old pending reconciliation jobs to critical review."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(hours=6)
        stale_jobs = (
            db.query(ReconciliationJob)
            .filter(
                ReconciliationJob.status.in_(["PENDING", "REVIEW_REQUIRED"]),
                ReconciliationJob.created_at < cutoff,
            )
            .all()
        )
        for job in stale_jobs:
            job.status = "ESCALATED"
        db.commit()
        return {"escalated": len(stale_jobs)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.aggregate_fleet_health", bind=True, max_retries=0)
def aggregate_fleet_health(self) -> dict[str, int]:
    """Aggregate fleet risk metrics for operational dashboards."""
    db = SessionLocal()
    try:
        failing = db.execute(select(func.count()).where(Device.health_status.in_(["OFFLINE", "DEGRADED"]))).scalar_one() or 0
        drift_hotspots = (
            db.execute(select(func.count()).where(ReconciliationJob.status.in_(["PENDING", "ESCALATED"]))).scalar_one() or 0
        )
        queue_pressure = (
            db.execute(
                select(func.count()).where(DeviceCommand.status.in_([DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value]))
            ).scalar_one()
            or 0
        )
        backlog = db.execute(
            select(func.count()).where(ReconciliationJob.status.in_(["PENDING", "RUNNING", "REVIEW_REQUIRED", "ESCALATED"]))
        ).scalar_one() or 0
        runtime_rows = list(db.execute(select(DeviceRuntimeHealth)).scalars().all())
        high_risk = sum(1 for row in runtime_rows if row.operational_risk_level == "HIGH")
        medium_risk = sum(1 for row in runtime_rows if row.operational_risk_level == "MEDIUM")
        low_risk = sum(1 for row in runtime_rows if row.operational_risk_level == "LOW")
        metric = FleetHealthMetric(
            scope="GLOBAL",
            scope_id="global",
            office_health=max(0, 100 - int(failing * 5 + high_risk * 3)),
            regional_health=max(0, 100 - int(failing * 4 + medium_risk * 2 + high_risk * 4)),
            failing_devices=int(failing),
            drift_hotspots=int(drift_hotspots),
            firmware_risk_distribution={"low": low_risk, "medium": medium_risk, "high": high_risk},
            queue_pressure=int(queue_pressure),
            reconciliation_backlog=int(backlog),
        )
        db.add(metric)
        db.commit()
        return {"failing_devices": int(failing), "queue_pressure": int(queue_pressure), "backlog": int(backlog)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.apply_retention_policies", bind=True, max_retries=0)
def apply_retention_policies(self) -> dict[str, int]:
    """Prune aged operational records per retention policy."""
    db = SessionLocal()
    try:
        now = datetime.now(ZoneInfo("UTC"))
        snapshot_cutoff = now - timedelta(days=settings.snapshot_retention_days)
        history_cutoff = now - timedelta(days=settings.command_history_retention_days)
        reconciliation_cutoff = now - timedelta(days=settings.reconciliation_retention_days)
        metrics_cutoff = now - timedelta(days=settings.metrics_retention_days)

        deleted_snapshots = (
            db.query(DeviceStateSnapshot).filter(DeviceStateSnapshot.captured_at < snapshot_cutoff).delete(synchronize_session=False)
        )
        deleted_history = (
            db.query(CommandExecutionHistory).filter(CommandExecutionHistory.started_at < history_cutoff).delete(synchronize_session=False)
        )
        deleted_reconciliation = (
            db.query(ReconciliationJob)
            .filter(
                ReconciliationJob.created_at < reconciliation_cutoff,
                ReconciliationJob.status.in_(["COMPLETED", "REJECTED"]),
            )
            .delete(synchronize_session=False)
        )
        deleted_metrics = (
            db.query(FleetHealthMetric).filter(FleetHealthMetric.captured_at < metrics_cutoff).delete(synchronize_session=False)
        )
        db.commit()
        return {
            "snapshots": int(deleted_snapshots),
            "history": int(deleted_history),
            "reconciliation": int(deleted_reconciliation),
            "metrics": int(deleted_metrics),
        }
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.seed_firmware_certifications", bind=True, max_retries=0)
def seed_firmware_certifications(self) -> dict[str, int]:
    """Ensure baseline certification rows exist for known firmware."""
    db = SessionLocal()
    created = 0
    try:
        defaults = [
            {
                "firmware_version": "unknown",
                "certification_status": "UNCERTIFIED",
                "write_stability_score": 10,
                "rollout_recommendation": "read-only",
                "operational_notes": "Unknown firmware must run in restricted mode.",
            }
        ]
        for item in defaults:
            existing = db.execute(
                select(CertifiedFirmwareProfile).where(CertifiedFirmwareProfile.firmware_version == item["firmware_version"])
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(CertifiedFirmwareProfile(**item))
            created += 1
        db.commit()
        return {"created": created}
    finally:
        db.close()
