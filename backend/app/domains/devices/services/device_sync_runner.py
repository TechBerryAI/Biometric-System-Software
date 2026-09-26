"""Shared full-device pull used by POST /sync/device and the manual Celery job."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from zk.exception import ZKError

from app.ai.cache.redis_cache import AIResponseCache
from app.core.config import Settings
from app.domains.attendance.services.attendance_service import run_device_sync_detailed, run_user_sync
from app.domains.devices.connection import DeviceConnectionConfig
from app.domains.devices.services.device_command_service import device_session_lock, wait_for_correction_commands_clear
from app.domains.devices.services.device_registry_service import ensure_default_device, update_device_health
from app.domains.devices.services.device_service import DeviceService, format_device_connection_error
from app.domains.devices.services.sync_manager_service import get_or_create_sync_state
from app.shared.device_exceptions import DeviceFetchError, DeviceLockContentionError


def execute_device_sync(db: Session, *, settings: Settings, full_resync: bool = True) -> dict[str, object]:
    """
    Pull users + attendance from the terminal and persist them.

    Raises DeviceLockContentionError when the terminal is busy, or DeviceFetchError
    after marking the device OFFLINE when the ZK session fails.
    """
    registered = ensure_default_device(db, settings)
    connection = DeviceConnectionConfig.from_device(registered, settings)
    device_service = DeviceService(settings=settings, connection=connection)
    if not wait_for_correction_commands_clear(db, registered.name, settings=settings):
        raise DeviceLockContentionError(
            f"Device '{registered.name}' is busy. "
            "Wait a few seconds and retry sync."
        )
    lock_wait = max(int(settings.zk_device_timeout_seconds), 180)
    try:
        with device_session_lock(registered.name, settings, blocking_timeout=lock_wait):
            u_total, u_ins = run_user_sync(
                db,
                device=device_service,
                settings=settings,
                device_id=registered.name,
            )
            sync_result = run_device_sync_detailed(
                db,
                device=device_service,
                full_resync=full_resync,
                settings=settings,
                device_id=registered.name,
            )
    except DeviceLockContentionError:
        raise
    except (ZKError, DeviceFetchError, OSError) as exc:
        detail = format_device_connection_error(exc, settings=settings, connection=connection)
        update_device_health(db, status="OFFLINE", detail=detail, settings=settings)
        db.commit()
        raise DeviceFetchError(detail) from exc

    update_device_health(db, status="ONLINE", detail="sync_ok", settings=settings)
    sync_state = get_or_create_sync_state(db, registered.name)
    now = datetime.now(ZoneInfo("UTC"))
    sync_state.last_user_sync_at = now
    sync_state.last_attendance_sync_at = now
    sync_state.sync_generation += 1
    cache = AIResponseCache(settings)
    cache.delete_prefix("ai:management:")
    cache.delete_prefix("ai:report:")
    cache.delete_prefix("ai:copilot:")
    cache.delete_prefix("ai:anomaly:")
    db.commit()
    return {
        "users_on_device": u_total,
        "new_employees": u_ins,
        "attendance_records_fetched": sync_result.fetched,
        "new_attendance_logs": sync_result.inserted,
        "placeholder_employees_created": sync_result.placeholders,
        "skipped_reason": sync_result.skipped_reason,
        "skipped_corrected_punches": sync_result.skipped_corrected_punches,
        "punches_missing_after_insert": sync_result.punches_missing_after_insert,
    }
