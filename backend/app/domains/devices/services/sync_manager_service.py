"""Per-device sync orchestration with conflict resolution."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.attendance.services.attendance_service import (
    MergedAttendanceSource,
    MergedUserSource,
    run_device_sync,
    run_user_sync,
)
from app.domains.devices.gateway.router import DeviceGateway, get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_sync_state import DeviceSyncState
from app.domains.devices.services.device_command_service import device_session_lock, wait_for_correction_commands_clear
from app.domains.devices.services.device_registry_service import update_device_health_for_device
from app.shared.device_exceptions import DeviceLockContentionError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def get_or_create_sync_state(db: Session, device_id: str) -> DeviceSyncState:
    row = db.execute(select(DeviceSyncState).where(DeviceSyncState.device_id == device_id)).scalar_one_or_none()
    if row is not None:
        return row
    row = DeviceSyncState(device_id=device_id)
    db.add(row)
    db.flush()
    return row


def _sync_sources_for_device(
    gateway: DeviceGateway,
    device: Device,
) -> tuple[object, object]:
    """Return (user_source, attendance_source) for the device connectivity mode."""
    mode = (device.connectivity_mode or "pull").lower()
    if mode == "push":
        push = gateway.get_push_connector(device)
        return push, push
    if mode == "both":
        pull = gateway.get_connector(device)
        push = gateway.get_push_connector(device)
        pull_svc = pull.service
        return MergedUserSource(pull_svc, push), MergedAttendanceSource(pull_svc, push)
    pull = gateway.get_connector(device)
    return pull.service, pull.service


def sync_device(
    db: Session,
    device: Device,
    *,
    full_resync: bool = True,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> dict[str, int]:
    """Run user + attendance sync for a single fleet device."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    device_id = device.name

    if not wait_for_correction_commands_clear(db, device_id, settings=settings):
        logger.warning("Deferring sync for %s: active correction commands", device_id)
        return {
            "skipped": 1,
            "users_fetched": 0,
            "users_upserted": 0,
            "fetched": 0,
            "inserted": 0,
            "placeholder_employees": 0,
        }

    user_source, attendance_source = _sync_sources_for_device(gateway, device)

    try:
        with device_session_lock(device_id, settings):
            users_fetched, users_upserted = run_user_sync(
                db, device=user_source, settings=settings, device_id=device_id
            )
            fetched, inserted, placeholders = run_device_sync(
                db,
                device=attendance_source,
                settings=settings,
                full_resync=full_resync,
                device_id=device_id,
            )
    except DeviceLockContentionError:
        return {
            "skipped": 1,
            "users_fetched": 0,
            "users_upserted": 0,
            "fetched": 0,
            "inserted": 0,
            "placeholder_employees": 0,
        }

    sync_state = get_or_create_sync_state(db, device_id)
    now = _utcnow()
    sync_state.last_user_sync_at = now
    sync_state.last_attendance_sync_at = now
    sync_state.sync_generation += 1
    update_device_health_for_device(db, device, status="ONLINE", detail="sync_ok")
    if (device.connectivity_mode or "pull").lower() in {"pull", "both"}:
        gateway.invalidate(device_id)

    return {
        "users_fetched": users_fetched,
        "users_upserted": users_upserted,
        "fetched": fetched,
        "inserted": inserted,
        "placeholder_employees": placeholders,
    }


def sync_all_pull_devices(
    db: Session,
    *,
    branch_id: str | None = None,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> list[dict[str, int | str]]:
    """Sync all active pull-mode devices, optionally filtered by branch."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    results: list[dict[str, int | str]] = []
    for device in gateway.list_pull_devices(db, branch_id=branch_id):
        device_id = device.name
        try:
            counts = sync_device(db, device, settings=settings, gateway=gateway)
            results.append({"device_id": device_id, **counts})
        except Exception as exc:  # noqa: BLE001
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("Rollback after sync failure failed device=%s", device_id, exc_info=True)
            logger.exception("Sync failed for device %s: %s", device_id, exc)
            try:
                update_device_health_for_device(db, device, status="OFFLINE", detail=str(exc))
            except Exception:  # noqa: BLE001
                logger.debug("Health update after sync failure failed device=%s", device_id, exc_info=True)
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            results.append({"device_id": device_id, "error": str(exc)})
    return results
