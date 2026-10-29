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
    run_device_sync_detailed,
    run_user_sync,
)
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.gateway.router import DeviceGateway, get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_sync_state import DeviceSyncState
from app.domains.devices.services.device_command_service import device_session_lock, wait_for_correction_commands_clear
from app.domains.devices.services.device_registry_service import update_device_health_for_device
from app.domains.devices.services.device_service import DeviceService
from app.shared.device_exceptions import DeviceFetchError, DeviceLockContentionError

logger = logging.getLogger(__name__)

_SKIPPED_SYNC: dict[str, int | str] = {
    "users_fetched": 0,
    "users_upserted": 0,
    "fetched": 0,
    "inserted": 0,
    "placeholder_employees": 0,
    "skipped_corrected_punches": 0,
    "punches_missing_after_insert": 0,
}


def _skipped_sync(reason: str, *, detail: str = "") -> dict[str, int | str]:
    out: dict[str, int | str] = {"skipped": 1, "skipped_reason": reason, **_SKIPPED_SYNC}
    if detail:
        out["detail"] = detail
    return out


def _preflight_device_tcp(device: Device, settings: Settings) -> tuple[bool, str]:
    connection = DeviceConnectionConfig.from_device(device, settings)
    return DeviceService(settings=settings, connection=connection).probe_tcp_connection()


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
        logger.warning("Deferring sync for %s: another device operation is in progress", device_id)
        return _skipped_sync("correction_active")

    user_source, attendance_source = _sync_sources_for_device(gateway, device)

    # Push-only devices are read from offline_buffer and are often not reachable over TCP.
    if (device.connectivity_mode or "pull").lower() in {"pull", "both"}:
        tcp_ok, tcp_detail = _preflight_device_tcp(device, settings)
        if not tcp_ok:
            logger.info("Skipping sync for %s — device TCP unreachable: %s", device_id, tcp_detail)
            update_device_health_for_device(db, device, status="OFFLINE", detail=tcp_detail)
            return _skipped_sync("device_unreachable", detail=tcp_detail)

    try:
        with device_session_lock(device_id, settings):
            users_fetched, users_upserted = run_user_sync(
                db, device=user_source, settings=settings, device_id=device_id
            )
            sync_result = run_device_sync_detailed(
                db,
                device=attendance_source,
                settings=settings,
                full_resync=full_resync,
                device_id=device_id,
            )
    except DeviceLockContentionError:
        return _skipped_sync("lock_contention")
    except DeviceFetchError as exc:
        detail = str(exc)
        logger.warning("Sync failed for %s: %s", device_id, detail)
        update_device_health_for_device(db, device, status="OFFLINE", detail=detail)
        return _skipped_sync("device_fetch_failed", detail=detail)

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
        "fetched": sync_result.fetched,
        "inserted": sync_result.inserted,
        "placeholder_employees": sync_result.placeholders,
        "skipped_corrected_punches": sync_result.skipped_corrected_punches,
        "punches_missing_after_insert": sync_result.punches_missing_after_insert,
        "skipped_reason": sync_result.skipped_reason,
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
        except DeviceFetchError as exc:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("Rollback after sync failure failed device=%s", device_id, exc_info=True)
            detail = str(exc)
            logger.warning("Sync failed for device %s: %s", device_id, detail)
            try:
                update_device_health_for_device(db, device, status="OFFLINE", detail=detail)
            except Exception:  # noqa: BLE001
                logger.debug("Health update after sync failure failed device=%s", device_id, exc_info=True)
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            results.append({"device_id": device_id, "error": detail})
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
