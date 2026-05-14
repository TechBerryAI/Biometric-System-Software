"""Enterprise operations center endpoints for reliability workflows."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.certified_firmware_profile import CertifiedFirmwareProfile
from app.models.command_execution_history import CommandExecutionHistory
from app.models.device import Device
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.models.device_firmware_profile import DeviceFirmwareProfile
from app.models.device_runtime_health import DeviceRuntimeHealth
from app.models.device_state_snapshot import DeviceStateSnapshot
from app.models.device_sync_event import DeviceSyncEvent
from app.models.fleet_health_metric import FleetHealthMetric
from app.models.reconciliation_job import ReconciliationJob
from app.models.system_control_state import SystemControlState

router = APIRouter(prefix="/operations", tags=["operations-center"])


@router.get("/queue", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def operations_queue(db: Session = Depends(get_db)) -> dict[str, object]:
    now = datetime.now(ZoneInfo("UTC"))
    starvation_cutoff = now - timedelta(minutes=10)
    queue_depth = db.execute(
        select(func.count()).where(
            DeviceCommand.status.in_(
                [
                    DeviceCommandStatus.PENDING.value,
                    DeviceCommandStatus.RETRYING.value,
                    DeviceCommandStatus.RUNNING.value,
                    DeviceCommandStatus.VERIFYING.value,
                ]
            )
        )
    ).scalar_one() or 0
    starving = db.execute(
        select(func.count()).where(
            DeviceCommand.status.in_([DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value]),
            DeviceCommand.created_at < starvation_cutoff,
        )
    ).scalar_one() or 0
    lock_contentions = db.execute(
        select(func.count()).where(DeviceSyncEvent.event_type == "LOCK_CONTENTION")
    ).scalar_one() or 0
    replay_recovered = db.execute(
        select(func.count()).where(CommandExecutionHistory.final_status == "RECOVERED_SUCCESS")
    ).scalar_one() or 0
    oldest_pending = db.execute(
        select(DeviceCommand.created_at)
        .where(DeviceCommand.status.in_([DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value]))
        .order_by(DeviceCommand.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "queue_depth": int(queue_depth),
        "queue_starvation": int(starving),
        "lock_contentions": int(lock_contentions),
        "replay_recovered_success": int(replay_recovered),
        "oldest_pending_at": oldest_pending,
    }


@router.get("/reconciliation", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def operations_reconciliation(db: Session = Depends(get_db)) -> dict[str, object]:
    rows = (
        db.execute(
            select(ReconciliationJob.status, func.count())
            .group_by(ReconciliationJob.status)
        ).all()
    )
    by_status = {status: int(count) for status, count in rows}
    recent = list(
        db.execute(
            select(ReconciliationJob)
            .order_by(ReconciliationJob.created_at.desc())
            .limit(20)
        ).scalars().all()
    )
    return {
        "status_counts": by_status,
        "recent_jobs": [
            {
                "id": row.id,
                "job_type": row.job_type,
                "target_entity": row.target_entity,
                "status": row.status,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in recent
        ],
    }


@router.get("/device-drift", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def operations_device_drift(db: Session = Depends(get_db)) -> dict[str, object]:
    snapshots = list(
        db.execute(
            select(DeviceStateSnapshot)
            .where(DeviceStateSnapshot.snapshot_type == "PERIODIC")
            .order_by(DeviceStateSnapshot.captured_at.desc())
            .limit(100)
        ).scalars().all()
    )
    latest_by_device: dict[str, DeviceStateSnapshot] = {}
    previous_by_device: dict[str, DeviceStateSnapshot] = {}
    for row in snapshots:
        if row.device_id not in latest_by_device:
            latest_by_device[row.device_id] = row
        elif row.device_id not in previous_by_device:
            previous_by_device[row.device_id] = row
    drifted = []
    for device_id, latest in latest_by_device.items():
        previous = previous_by_device.get(device_id)
        if previous is None:
            continue
        if latest.snapshot_hash != previous.snapshot_hash:
            drifted.append(
                {
                    "device_id": device_id,
                    "latest_captured_at": latest.captured_at,
                    "previous_captured_at": previous.captured_at,
                    "latest_user_count": latest.user_count,
                    "previous_user_count": previous.user_count,
                }
            )
    drift_events_24h = db.execute(
        select(func.count()).where(
            DeviceSyncEvent.event_type == "RECONCILIATION",
            DeviceSyncEvent.status == "DRIFT",
            DeviceSyncEvent.timestamp >= (datetime.now(ZoneInfo("UTC")) - timedelta(hours=24)),
        )
    ).scalar_one() or 0
    return {
        "drifted_devices": drifted,
        "drifted_device_count": len(drifted),
        "drift_events_last_24h": int(drift_events_24h),
    }


@router.get("/firmware-health", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def operations_firmware_health(db: Session = Depends(get_db)) -> dict[str, object]:
    devices = list(db.execute(select(Device).order_by(Device.name.asc())).scalars().all())
    profile_versions = {
        row.firmware_version
        for row in db.execute(select(DeviceFirmwareProfile.firmware_version)).scalars().all()
        if row
    }
    unknown = [dev for dev in devices if (dev.firmware_version or "unknown") not in profile_versions]
    return {
        "device_count": len(devices),
        "unknown_firmware_profile_count": len(unknown),
        "uncertified_firmware_count": int(
            db.execute(
                select(func.count()).select_from(CertifiedFirmwareProfile).where(
                    CertifiedFirmwareProfile.certification_status.in_(["UNCERTIFIED", "UNSTABLE"])
                )
            ).scalar_one()
            or 0
        ),
        "devices": [
            {
                "device_uuid": dev.device_uuid,
                "name": dev.name,
                "firmware_version": dev.firmware_version,
                "health_status": dev.health_status,
            }
            for dev in devices
        ],
    }


@router.get("/firmware-certification", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def firmware_certification_dashboard(db: Session = Depends(get_db)) -> dict[str, object]:
    rows = list(
        db.execute(
            select(CertifiedFirmwareProfile).order_by(CertifiedFirmwareProfile.write_stability_score.desc())
        ).scalars().all()
    )
    return {
        "profiles": [
            {
                "firmware_version": row.firmware_version,
                "certification_status": row.certification_status,
                "write_stability_score": row.write_stability_score,
                "rollout_recommendation": row.rollout_recommendation,
                "verification_strategy": row.verification_strategy,
            }
            for row in rows
        ]
    }


@router.get("/fleet-health", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def fleet_health(db: Session = Depends(get_db)) -> dict[str, object]:
    failing_devices = (
        db.execute(select(func.count()).where(Device.health_status.in_(["OFFLINE", "DEGRADED"]))).scalar_one() or 0
    )
    quarantined = db.execute(select(func.count()).where(Device.mode == "QUARANTINED")).scalar_one() or 0
    runtime_rows = list(db.execute(select(DeviceRuntimeHealth)).scalars().all())
    risk_buckets = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for row in runtime_rows:
        risk_buckets[row.operational_risk_level] = risk_buckets.get(row.operational_risk_level, 0) + 1
    queue_pressure = db.execute(
        select(func.count()).where(
            DeviceCommand.status.in_([DeviceCommandStatus.PENDING.value, DeviceCommandStatus.RETRYING.value])
        )
    ).scalar_one() or 0
    backlog = db.execute(
        select(func.count()).where(ReconciliationJob.status.in_(["PENDING", "RUNNING", "REVIEW_REQUIRED", "ESCALATED"]))
    ).scalar_one() or 0
    return {
        "failing_devices": int(failing_devices),
        "quarantined_devices": int(quarantined),
        "runtime_risk_distribution": risk_buckets,
        "queue_pressure": int(queue_pressure),
        "reconciliation_backlog": int(backlog),
    }


@router.get("/incident-timeline", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def incident_timeline(
    limit: int = Query(200, ge=10, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    events = list(
        db.execute(
            select(DeviceSyncEvent)
            .where(DeviceSyncEvent.status.in_(["FAILED", "DRIFT", "RETRYING", "BLOCKED", "REJECTED"]))
            .order_by(DeviceSyncEvent.timestamp.desc())
            .limit(limit)
        ).scalars().all()
    )
    return {
        "events": [
            {
                "timestamp": row.timestamp,
                "device_id": row.device_id,
                "event_type": row.event_type,
                "status": row.status,
                "source": row.event_source,
                "details": row.details,
            }
            for row in events
        ]
    }


@router.get("/alerts", dependencies=[Depends(require_permissions(Permission.METRICS_READ))])
def operations_alerts(db: Session = Depends(get_db)) -> dict[str, object]:
    alerts: list[dict[str, str | int]] = []
    lock_contention = db.execute(select(func.count()).where(DeviceSyncEvent.event_type == "LOCK_CONTENTION")).scalar_one() or 0
    if lock_contention > 20:
        alerts.append({"severity": "high", "type": "lock_contention", "value": int(lock_contention)})
    backlog = db.execute(
        select(func.count()).where(ReconciliationJob.status.in_(["PENDING", "RUNNING", "REVIEW_REQUIRED", "ESCALATED"]))
    ).scalar_one() or 0
    if backlog > 50:
        alerts.append({"severity": "high", "type": "reconciliation_backlog", "value": int(backlog)})
    dead = db.execute(select(func.count()).where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)).scalar_one() or 0
    if dead > 0:
        alerts.append({"severity": "medium", "type": "dead_letter_commands", "value": int(dead)})
    quarantined = db.execute(select(func.count()).where(Device.mode == "QUARANTINED")).scalar_one() or 0
    if quarantined > 0:
        alerts.append({"severity": "high", "type": "quarantined_devices", "value": int(quarantined)})
    governance = db.execute(select(SystemControlState).where(SystemControlState.singleton_key == "global")).scalar_one_or_none()
    if governance is not None and governance.emergency_freeze_mode:
        alerts.append({"severity": "critical", "type": "emergency_freeze_mode", "value": 1})
    latest_fleet = db.execute(
        select(FleetHealthMetric).order_by(FleetHealthMetric.captured_at.desc()).limit(1)
    ).scalar_one_or_none()
    if latest_fleet is not None and latest_fleet.office_health < 70:
        alerts.append({"severity": "medium", "type": "fleet_health_drop", "value": int(latest_fleet.office_health)})
    return {"alerts": alerts}


@router.get("/dead-letters", dependencies=[Depends(require_permissions(Permission.DEVICE_MANAGE))])
def operations_dead_letters(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rows = list(
        db.execute(
            select(DeviceCommand)
            .where(DeviceCommand.status == DeviceCommandStatus.DEAD_LETTER.value)
            .order_by(DeviceCommand.completed_at.desc(), DeviceCommand.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )
    return {
        "count": len(rows),
        "items": [
            {
                "command_uuid": row.command_uuid,
                "device_id": row.device_id,
                "command_type": row.command_type,
                "retries": row.retries,
                "last_error": row.last_error,
                "correlation_id": row.correlation_id,
                "completed_at": row.completed_at,
            }
            for row in rows
        ],
    }
