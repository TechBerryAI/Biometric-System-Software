"""Device heartbeat and connectivity probing."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.devices.gateway.router import DeviceGateway, get_device_gateway
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_sync_state import DeviceSyncState
from app.domains.devices.services.device_command_service import device_session_lock
from app.domains.devices.services.device_registry_service import update_device_health_for_device
from app.shared.device_exceptions import DeviceLockContentionError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("UTC"))


def _recent_connectivity_evidence(
    db: Session,
    device: Device,
    *,
    settings: Settings,
) -> bool:
    """True when we recently proved the device was reachable (sync or last_seen)."""
    grace = timedelta(seconds=max(settings.device_poll_interval_seconds * 3, 600))
    now = _utcnow()
    last_seen = _aware_utc(device.last_seen)
    if last_seen is not None and (now - last_seen) <= grace:
        return True
    sync_state = db.execute(
        select(DeviceSyncState).where(DeviceSyncState.device_id == device.name)
    ).scalar_one_or_none()
    last_sync = _aware_utc(sync_state.last_attendance_sync_at if sync_state else None)
    return bool(last_sync is not None and (now - last_sync) <= grace)


def probe_device_heartbeat(
    db: Session,
    device: Device,
    *,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> dict[str, object]:
    """Probe a single device and update health status.

    Never mark OFFLINE solely because another sync holds the ZK session lock — terminals
    typically allow only one TCP client, so a concurrent probe would false-fail.
    """
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    device_id = device.name
    previous_status = (device.health_status or "").upper()
    recent_ok = _recent_connectivity_evidence(db, device, settings=settings)
    try:
        # Non-blocking: if sync/command holds the lock, skip probe and keep prior health.
        with device_session_lock(device_id, settings, blocking_timeout=0):
            ok, detail = gateway.probe_device(device)
            if ok:
                update_device_health_for_device(db, device, status="ONLINE", detail=detail)
                fingerprint = gateway.get_connector(device).detect_firmware_fingerprint()
                fw = fingerprint.get("firmware_version")
                if fw and fw != "unknown":
                    device.firmware_version = str(fw)
                serial = fingerprint.get("serial_number")
                if serial:
                    device.serial_number = str(serial)
                if previous_status == "OFFLINE" and settings.device_auto_sync_enabled:
                    _enqueue_catchup_sync(device_id=device_id)
                return {
                    "device_id": device_id,
                    "online": True,
                    "detail": detail,
                    "probed_at": _utcnow().isoformat(),
                    "catchup_sync_enqueued": bool(
                        previous_status == "OFFLINE" and settings.device_auto_sync_enabled
                    ),
                }

            if recent_ok:
                # Recent successful sync/last_seen is stronger than a flaky probe — stay Healthy.
                if previous_status != "ONLINE":
                    update_device_health_for_device(
                        db, device, status="ONLINE", detail=f"grace_keep_online:{detail}"
                    )
                logger.info(
                    "Probe failed for %s but recent sync/last_seen within grace; keeping ONLINE (%s)",
                    device_id,
                    detail,
                )
                return {
                    "device_id": device_id,
                    "online": True,
                    "detail": f"probe_soft_fail:{detail}",
                    "probed_at": _utcnow().isoformat(),
                    "catchup_sync_enqueued": False,
                    "skipped_reason": "recent_connectivity_grace",
                }

            update_device_health_for_device(db, device, status="OFFLINE", detail=detail)
            return {
                "device_id": device_id,
                "online": False,
                "detail": detail,
                "probed_at": _utcnow().isoformat(),
                "catchup_sync_enqueued": False,
            }
    except DeviceLockContentionError:
        # Sync in progress already proves the device is reachable.
        if previous_status != "ONLINE":
            try:
                update_device_health_for_device(db, device, status="ONLINE", detail="busy_assume_online")
            except Exception:  # noqa: BLE001
                logger.debug("Could not set ONLINE while lock busy for %s", device_id, exc_info=True)
        logger.info("Skipping connectivity probe for %s — device I/O lock busy (sync in progress)", device_id)
        return {
            "device_id": device_id,
            "online": True,
            "detail": "device_busy_skip_probe",
            "probed_at": _utcnow().isoformat(),
            "catchup_sync_enqueued": False,
            "skipped_reason": "device_lock_busy",
        }
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Rollback after heartbeat failure failed device=%s", device_id, exc_info=True)
        logger.warning("Heartbeat probe failed for %s: %s", device_id, exc)
        if recent_ok:
            try:
                if previous_status != "ONLINE":
                    update_device_health_for_device(
                        db, device, status="ONLINE", detail=f"grace_keep_online:{exc}"
                    )
            except Exception:  # noqa: BLE001
                logger.debug("Grace ONLINE update failed for %s", device_id, exc_info=True)
            logger.info(
                "Probe exception for %s within grace window; keeping ONLINE (%s)",
                device_id,
                exc,
            )
            return {
                "device_id": device_id,
                "online": True,
                "detail": f"probe_exception_soft_fail:{exc}",
                "probed_at": _utcnow().isoformat(),
                "skipped_reason": "recent_connectivity_grace",
            }
        try:
            update_device_health_for_device(db, device, status="OFFLINE", detail=str(exc))
        except Exception:  # noqa: BLE001
            logger.debug("Health update after heartbeat failure failed device=%s", device_id, exc_info=True)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {"device_id": device_id, "online": False, "detail": str(exc), "probed_at": _utcnow().isoformat()}


def _enqueue_catchup_sync(*, device_id: str) -> None:
    """When a device returns from OFFLINE, pull attendance immediately (don't wait for beat)."""
    try:
        from app.workers.tasks import sync_attendance_from_device

        sync_attendance_from_device.delay()
        logger.info("Enqueued catch-up attendance sync after %s returned ONLINE", device_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to enqueue catch-up sync for %s: %s", device_id, exc)


def probe_all_devices(
    db: Session,
    *,
    branch_id: str | None = None,
    settings: Settings | None = None,
    gateway: DeviceGateway | None = None,
) -> list[dict[str, object]]:
    """Probe all active pull-mode devices."""
    settings = settings or get_settings()
    gateway = gateway or get_device_gateway(settings)
    results: list[dict[str, object]] = []
    for device in gateway.list_pull_devices(db, branch_id=branch_id):
        results.append(probe_device_heartbeat(db, device, settings=settings, gateway=gateway))
    return results
