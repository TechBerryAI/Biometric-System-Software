"""Operational APIs for audit logs and command queue observability."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.privileged_account import is_privileged_account
from app.core.security import Permission, get_current_user, require_permissions
from app.models.audit_log import AuditLog
from app.models.certified_firmware_profile import CertifiedFirmwareProfile
from app.models.command_execution_history import CommandExecutionHistory
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_firmware_profile import DeviceFirmwareProfile
from app.models.device_state_snapshot import DeviceStateSnapshot
from app.models.device_sync_event import DeviceSyncEvent
from app.models.reconciliation_job import ReconciliationJob
from app.models.system_control_state import SystemControlState
from app.models.user import User
from app.schemas.audit import AuditLogRead
from app.schemas.device_command import DeviceCommandRead
from app.services.attendance_correction_service import finalize_pending_correction_for_command
from app.services.device_command_service import INTERNAL_AUDIT_ACTIONS, INTERNAL_COMMAND_TYPES, reprocess_device_command
from app.services.device_registry_service import ensure_default_device

router = APIRouter(prefix="/ops", tags=["operations"])


class CertifiedFirmwareUpsert(BaseModel):
    firmware_version: str = Field(min_length=1, max_length=128)
    certification_status: str = Field(default="CERTIFIED")
    write_stability_score: int = Field(default=80, ge=0, le=100)
    device_family: str | None = None
    vendor: str | None = None
    rollout_recommendation: str | None = None
    operational_notes: str | None = None


class OperationalMetricsRead(BaseModel):
    queue_depth: int
    stale_commands: int
    dead_letter_commands: int
    failing_devices: int
    sync_drift_events: int
    verification_failures: int
    reconciliation_pending: int
    replay_recovered_success: int
    lock_contention_events: int
    commands_currently_verifying: int
    snapshot_events_last_24h: int
    quarantined_devices: int
    emergency_freeze_active: int
    device_health_status: str
    device_ip: str
    device_port: int
    device_auto_sync_enabled: bool


@router.get("/audit-logs", response_model=list[AuditLogRead], dependencies=[Depends(require_permissions(Permission.AUDIT_READ))])
def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    rows = list(db.execute(query).scalars().all())
    if not is_privileged_account(user):
        rows = [row for row in rows if row.action_type not in INTERNAL_AUDIT_ACTIONS]
    return rows


@router.get(
    "/device-commands",
    response_model=list[DeviceCommandRead],
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def list_device_commands(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeviceCommand]:
    query = select(DeviceCommand).order_by(DeviceCommand.created_at.desc()).limit(limit)
    if status:
        query = query.where(DeviceCommand.status == status)
    rows = list(db.execute(query).scalars().all())
    if not is_privileged_account(user):
        rows = [row for row in rows if row.command_type not in INTERNAL_COMMAND_TYPES]
    return rows


@router.post(
    "/device-commands/{command_uuid}/process",
    response_model=DeviceCommandRead,
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def process_device_command_now(
    command_uuid: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceCommand:
    command = db.execute(select(DeviceCommand).where(DeviceCommand.command_uuid == command_uuid)).scalar_one_or_none()
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    if command.command_type in INTERNAL_COMMAND_TYPES and not is_privileged_account(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device command not found.")
    try:
        command = reprocess_device_command(db, command_uuid, worker_id="api-ops-reprocess")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if (
        command.command_type == "CORRECT_ATTENDANCE"
        and command.status == DeviceCommandStatus.SUCCESS.value
    ):
        finalize_pending_correction_for_command(db, command_uuid)
        db.refresh(command)
    return command


@router.post(
    "/firmware-certifications",
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def upsert_firmware_certification(
    payload: CertifiedFirmwareUpsert,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = db.execute(
        select(CertifiedFirmwareProfile).where(CertifiedFirmwareProfile.firmware_version == payload.firmware_version)
    ).scalar_one_or_none()
    if row is None:
        row = CertifiedFirmwareProfile(
            firmware_version=payload.firmware_version,
            certification_status=payload.certification_status,
            write_stability_score=payload.write_stability_score,
            device_family=payload.device_family,
            vendor=payload.vendor,
            rollout_recommendation=payload.rollout_recommendation,
            operational_notes=payload.operational_notes,
            supported_operations={"operations": ["UPSERT_USER"]},
            unsafe_operations={"operations": ["UID_REWRITE", "CARD_REWRITE", "PRIVILEGE_REWRITE"]},
        )
        db.add(row)
    else:
        row.certification_status = payload.certification_status
        row.write_stability_score = payload.write_stability_score
        row.device_family = payload.device_family
        row.vendor = payload.vendor
        row.rollout_recommendation = payload.rollout_recommendation
        row.operational_notes = payload.operational_notes
    db.commit()
    return {
        "firmware_version": row.firmware_version,
        "certification_status": row.certification_status,
        "write_stability_score": row.write_stability_score,
    }


@router.get(
    "/firmware-profiles",
    dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))],
)
def list_firmware_profiles(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = list(
        db.execute(select(DeviceFirmwareProfile).order_by(DeviceFirmwareProfile.firmware_version.asc())).scalars().all()
    )
    return [
        {
            "firmware_version": row.firmware_version,
            "supports_user_write": row.supports_user_write,
            "supports_name_update": row.supports_name_update,
            "supports_uid_update": row.supports_uid_update,
            "supports_card_update": row.supports_card_update,
            "safe_write_strategy": row.safe_write_strategy,
            "reconnect_required": row.reconnect_required,
            "write_delay_ms": row.write_delay_ms,
            "verification_strategy": row.verification_strategy,
            "known_limitations": row.known_limitations,
        }
        for row in rows
    ]


@router.get(
    "/reconciliation-jobs",
    dependencies=[Depends(require_permissions(Permission.METRICS_READ))],
)
def list_reconciliation_jobs(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    query = select(ReconciliationJob).order_by(ReconciliationJob.created_at.desc()).limit(limit)
    if status:
        query = query.where(ReconciliationJob.status == status)
    jobs = list(db.execute(query).scalars().all())
    return [
        {
            "id": job.id,
            "job_type": job.job_type,
            "target_entity": job.target_entity,
            "status": job.status,
            "findings": job.findings,
            "resolution": job.resolution,
            "correlation_id": job.correlation_id,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
        }
        for job in jobs
    ]


@router.get(
    "/metrics",
    response_model=OperationalMetricsRead,
    dependencies=[Depends(require_permissions(Permission.METRICS_READ))],
)
def operational_metrics(db: Session = Depends(get_db)) -> OperationalMetricsRead:
    stale_cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(minutes=15)
    queue_depth = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status.in_(
                    [
                        DeviceCommandStatus.PENDING.value,
                        DeviceCommandStatus.RUNNING.value,
                        DeviceCommandStatus.RETRYING.value,
                        DeviceCommandStatus.VERIFYING.value,
                        DeviceCommandStatus.FAILED.value,
                    ]
                )
            )
        ).scalar_one()
        or 0
    )
    stale_commands = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.status.in_([DeviceCommandStatus.RUNNING.value, DeviceCommandStatus.VERIFYING.value]),
                or_(
                    DeviceCommand.heartbeat_at < stale_cutoff,
                    and_(DeviceCommand.heartbeat_at.is_(None), DeviceCommand.started_at < stale_cutoff),
                ),
            )
        ).scalar_one()
        or 0
    )
    dead_letters = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)).scalar_one()
        or 0
    )
    failing_devices = (
        db.execute(select(func.count()).where(Device.health_status.in_(["OFFLINE", "DEGRADED"]))).scalar_one()
        or 0
    )
    sync_lag_events = (
        db.execute(
            select(func.count()).where(
                DeviceSyncEvent.event_type == "RECONCILIATION",
                DeviceSyncEvent.status == "DRIFT",
            )
        ).scalar_one()
        or 0
    )
    verification_failures = (
        db.execute(
            select(func.count()).where(
                DeviceCommand.verification_status == "FAILED",
            )
        ).scalar_one()
        or 0
    )
    reconciliation_pending = (
        db.execute(
            select(func.count()).where(
                ReconciliationJob.status.in_(["PENDING", "RUNNING"]),
            )
        ).scalar_one()
        or 0
    )
    replay_recovered = (
        db.execute(select(func.count()).where(CommandExecutionHistory.final_status == "RECOVERED_SUCCESS")).scalar_one()
        or 0
    )
    lock_contention = (
        db.execute(select(func.count()).where(DeviceSyncEvent.event_type == "LOCK_CONTENTION")).scalar_one() or 0
    )
    verification_latency_events = (
        db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.VERIFYING.value)).scalar_one()
        or 0
    )
    recent_drift = (
        db.execute(
            select(func.count()).where(
                DeviceStateSnapshot.snapshot_type == "PERIODIC",
                DeviceStateSnapshot.captured_at >= datetime.now(ZoneInfo("UTC")) - timedelta(hours=24),
            )
        ).scalar_one()
        or 0
    )
    quarantined_devices = db.execute(select(func.count()).where(Device.mode == "QUARANTINED")).scalar_one() or 0
    emergency_freeze = (
        db.execute(
            select(func.count()).where(
                SystemControlState.singleton_key == "global",
                SystemControlState.emergency_freeze_mode.is_(True),
            )
        ).scalar_one()
        or 0
    )
    settings = get_settings()
    registered_device = db.execute(select(Device).where(Device.name == settings.zk_device_id)).scalar_one_or_none()
    if registered_device is None:
        registered_device = ensure_default_device(db, settings=settings)
    device_health_status = (
        "MANUAL" if not settings.device_auto_sync_enabled else registered_device.health_status
    )
    effective_failing_devices = (
        0 if not settings.device_auto_sync_enabled else int(failing_devices)
    )
    return OperationalMetricsRead(
        queue_depth=int(queue_depth),
        stale_commands=int(stale_commands),
        dead_letter_commands=int(dead_letters),
        failing_devices=effective_failing_devices,
        sync_drift_events=int(sync_lag_events),
        verification_failures=int(verification_failures),
        reconciliation_pending=int(reconciliation_pending),
        replay_recovered_success=int(replay_recovered),
        lock_contention_events=int(lock_contention),
        commands_currently_verifying=int(verification_latency_events),
        snapshot_events_last_24h=int(recent_drift),
        quarantined_devices=int(quarantined_devices),
        emergency_freeze_active=int(emergency_freeze),
        device_health_status=device_health_status,
        device_ip=registered_device.ip_address,
        device_port=registered_device.port,
        device_auto_sync_enabled=settings.device_auto_sync_enabled,
    )
