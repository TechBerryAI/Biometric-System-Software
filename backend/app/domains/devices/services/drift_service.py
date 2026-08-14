"""Persist and resolve device user drift from reconciliation."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.devices.models.device_user_drift import DeviceUserDrift
from app.domains.employees.models.device_user_mapping import DeviceUserMapping

logger = logging.getLogger(__name__)

DRIFT_MISSING_ON_DEVICE = "missing_on_device"
DRIFT_MISSING_MAPPING = "missing_mapping"


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def persist_drift_events(
    db: Session,
    *,
    device_id: str,
    missing_on_device: list[str],
    missing_mapping: list[str],
    tenant_id: int | None = None,
) -> dict[str, int]:
    """Upsert open drift rows and resolve ones that no longer apply."""
    open_rows = list(
        db.execute(
            select(DeviceUserDrift).where(
                DeviceUserDrift.device_id == device_id,
                DeviceUserDrift.status == "open",
            )
        ).scalars().all()
    )
    open_keys = {(r.device_user_id, r.drift_type): r for r in open_rows}

    created = 0
    resolved = 0

    desired: dict[tuple[str, str], str | None] = {}
    for user_id in missing_on_device:
        emp = db.execute(
            select(DeviceUserMapping.employee_uuid).where(
                DeviceUserMapping.device_id == device_id,
                DeviceUserMapping.device_user_id == user_id,
                DeviceUserMapping.active.is_(True),
            ).limit(1)
        ).scalar_one_or_none()
        desired[(user_id, DRIFT_MISSING_ON_DEVICE)] = emp

    for user_id in missing_mapping:
        desired[(user_id, DRIFT_MISSING_MAPPING)] = None

    for key, employee_uuid in desired.items():
        user_id, drift_type = key
        existing = open_keys.pop(key, None)
        if existing is None:
            db.add(
                DeviceUserDrift(
                    tenant_id=tenant_id,
                    device_id=device_id,
                    device_user_id=user_id,
                    drift_type=drift_type,
                    employee_uuid=employee_uuid,
                    status="open",
                )
            )
            created += 1

    # Remaining open keys are resolved (no longer drifting).
    now = _utcnow()
    for row in open_keys.values():
        row.status = "resolved"
        row.resolved_at = now
        row.resolution = "auto_cleared"
        resolved += 1

    db.flush()
    logger.info(
        "Drift persistence device=%s created=%s resolved=%s open=%s",
        device_id,
        created,
        resolved,
        len(desired),
    )
    return {"created": created, "resolved": resolved, "open": len(desired)}


def mark_drift_resolved(
    db: Session,
    drift_id: int,
    *,
    resolution: str,
    command_uuid: str | None = None,
) -> DeviceUserDrift | None:
    row = db.execute(select(DeviceUserDrift).where(DeviceUserDrift.id == drift_id)).scalar_one_or_none()
    if row is None:
        return None
    row.status = "resolved"
    row.resolved_at = _utcnow()
    row.resolution = resolution
    row.command_uuid = command_uuid
    db.flush()
    return row
