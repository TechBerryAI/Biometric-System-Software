"""Global governance and device mode policy checks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.system_control_state import SystemControlState


def ensure_control_state(db: Session) -> SystemControlState:
    row = db.execute(select(SystemControlState).where(SystemControlState.singleton_key == "global")).scalar_one_or_none()
    if row is not None:
        return row
    row = SystemControlState(singleton_key="global", maintenance_mode=False, emergency_freeze_mode=False)
    db.add(row)
    db.flush()
    return row


def assert_device_write_allowed(db: Session, *, device_id: str) -> tuple[bool, str | None]:
    control = ensure_control_state(db)
    if control.emergency_freeze_mode:
        return False, "Global emergency freeze is active."
    if control.maintenance_mode:
        return False, "Global maintenance mode is active."
    device = db.execute(select(Device).where(Device.name == device_id)).scalar_one_or_none()
    if device is not None and device.mode in {"READ_ONLY", "QUARANTINED", "OFFLINE"}:
        return False, f"Device mode '{device.mode}' blocks mutations."
    return True, None
