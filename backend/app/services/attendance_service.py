"""User sync, attendance log sync, and session rebuild."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee
from app.models.device_user_mapping import DeviceUserMapping
from app.services.attendance_helpers import (
    local_date as _local_date,
    rebuild_sessions_for_employee_date,
    rebuild_sessions_for_local_date,
    resolve_mapping_for_punch as _resolve_mapping_for_punch,
)
from app.services.device_service import DeviceAttendanceRecord, DeviceService, DeviceUser
from app.services.employee_offboard_service import enqueue_delete_user_command
from app.services.punch_classification import device_attendance_punch_type

logger = logging.getLogger(__name__)


def _incremental_sync_floor(db: Session, *, device_id: str, settings: Settings) -> datetime | None:
    """Use recent overlap window so incremental sync avoids reprocessing full history."""
    latest = db.execute(
        select(AttendanceLog.timestamp)
        .where(AttendanceLog.device_id == device_id)
        .order_by(AttendanceLog.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return None
    return latest - timedelta(minutes=settings.device_sync_overlap_minutes)


def _dedupe_device_records(
    records: Sequence[DeviceAttendanceRecord],
    *,
    settings: Settings,
) -> list[DeviceAttendanceRecord]:
    """Collapse noisy back-to-back duplicate punches produced by unstable device firmware."""
    window = timedelta(seconds=settings.duplicate_punch_window_seconds)
    if window.total_seconds() <= 0:
        return list(records)
    out: list[DeviceAttendanceRecord] = []
    last_seen: dict[tuple[str, int], datetime] = {}
    for row in sorted(records, key=lambda r: r.timestamp):
        key = (row.user_id, row.status)
        prev = last_seen.get(key)
        if prev is not None and row.timestamp - prev <= window:
            continue
        out.append(row)
        last_seen[key] = row.timestamp
    return out


def _ensure_active_mapping(
    db: Session,
    *,
    employee_uuid: str,
    device_id: str,
    device_user_id: str,
    effective_at: datetime,
) -> int:
    existing_for_identity = db.execute(
        select(DeviceUserMapping).where(
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.device_user_id == device_user_id,
            DeviceUserMapping.active.is_(True),
        )
    ).scalars().all()
    for mapping in existing_for_identity:
        if mapping.employee_uuid != employee_uuid:
            mapping.active = False
            mapping.valid_to = effective_at

    active_for_employee = db.execute(
        select(DeviceUserMapping).where(
            DeviceUserMapping.employee_uuid == employee_uuid,
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.active.is_(True),
        )
    ).scalars().all()
    for mapping in active_for_employee:
        if mapping.device_user_id == device_user_id:
            return mapping.id
        mapping.active = False
        mapping.valid_to = effective_at

    new_mapping = DeviceUserMapping(
        employee_uuid=employee_uuid,
        device_id=device_id,
        device_user_id=device_user_id,
        valid_from=effective_at,
        active=True,
    )
    db.add(new_mapping)
    db.flush()
    return new_mapping.id


def sync_employees_from_device_users(db: Session, users: Sequence[DeviceUser]) -> int:
    """Upsert device users into employees. Returns number of rows affected."""
    affected = 0
    now = datetime.now(ZoneInfo("UTC"))
    settings = get_settings()
    for u in users:
        departed = db.execute(
            select(Employee).where(
                Employee.device_user_id == u.user_id,
                Employee.departed_at.is_not(None),
            )
        ).scalar_one_or_none()
        if departed is not None:
            try:
                enqueue_delete_user_command(
                    db,
                    device_id=settings.zk_device_id,
                    user_id=u.user_id,
                    uid=u.uid,
                    initiated_from="sync:departed_cleanup",
                    process_inline=False,
                    settings=settings,
                )
            except RuntimeError:
                pass
            continue

        old_uid_identity = str(u.uid)
        if u.user_id != old_uid_identity:
            legacy = db.execute(
                select(Employee).where(Employee.device_user_id == old_uid_identity)
            ).scalar_one_or_none()
            existing_new = db.execute(
                select(Employee).where(Employee.device_user_id == u.user_id)
            ).scalar_one_or_none()
            if legacy is not None and existing_new is None:
                legacy.device_user_id = u.user_id
                legacy.name = u.name
                legacy.device_uid = u.uid
                legacy.device_privilege = u.privilege
                legacy.device_group_id = u.group_id
                legacy.device_card = u.card
                if not legacy.employee_uuid:
                    legacy.employee_uuid = str(uuid4())
                db.flush()

        stmt = (
            pg_insert(Employee)
            .values(
                employee_uuid=str(uuid4()),
                device_user_id=u.user_id,
                device_uid=u.uid,
                device_privilege=u.privilege,
                device_group_id=u.group_id,
                device_card=u.card,
                name=u.name,
                department=None,
                shift_start=None,
                shift_end=None,
            )
            .on_conflict_do_update(
                index_elements=[Employee.device_user_id],
                set_={
                    "name": u.name,
                    "device_uid": u.uid,
                    "device_privilege": u.privilege,
                    "device_group_id": u.group_id,
                    "device_card": u.card,
                },
            )
        )
        result = db.execute(stmt)
        rc = result.rowcount
        if rc is not None and rc > 0:
            affected += rc
        emp = db.execute(select(Employee).where(Employee.device_user_id == u.user_id)).scalar_one_or_none()
        if emp is None:
            continue
        if not emp.employee_uuid:
            emp.employee_uuid = str(uuid4())
            db.flush()
        _ensure_active_mapping(
            db,
            employee_uuid=emp.employee_uuid,
            device_id=settings.zk_device_id,
            device_user_id=u.user_id,
            effective_at=now,
        )
    db.commit()
    return affected


def insert_attendance_logs_idempotent(
    db: Session,
    records: Sequence[DeviceAttendanceRecord],
    device_id: str,
) -> int:
    """Insert raw logs; duplicates ignored via unique (device_id, employee_code, timestamp)."""
    rows = 0
    settings = get_settings()
    duplicate_window = timedelta(seconds=settings.duplicate_punch_window_seconds)
    for r in records:
        employee_code = r.user_id
        punch_type = device_attendance_punch_type(status=r.status, punch=r.punch)
        if duplicate_window.total_seconds() > 0:
            existing_near_duplicate = db.execute(
                select(AttendanceLog.id).where(
                    AttendanceLog.device_id == device_id,
                    AttendanceLog.employee_code == employee_code,
                    AttendanceLog.punch_type == punch_type,
                    AttendanceLog.timestamp >= r.timestamp - duplicate_window,
                    AttendanceLog.timestamp <= r.timestamp + duplicate_window,
                ).limit(1)
            ).scalar_one_or_none()
            if existing_near_duplicate is not None:
                logger.info(
                    "Skipping near-duplicate punch device=%s employee=%s ts=%s punch=%s",
                    device_id,
                    employee_code,
                    r.timestamp.isoformat(),
                    punch_type,
                )
                continue
        mapping = _resolve_mapping_for_punch(
            db,
            device_id=device_id,
            device_user_id=employee_code,
            at_time=r.timestamp,
        )
        stmt = (
            pg_insert(AttendanceLog)
            .values(
                employee_code=employee_code,
                timestamp=r.timestamp,
                device_id=device_id,
                employee_uuid=mapping.employee_uuid if mapping else None,
                device_mapping_id=mapping.id if mapping else None,
                punch_type=punch_type,
            )
            .on_conflict_do_nothing(constraint="uq_log_device_employee_ts")
        )
        res = db.execute(stmt)
        rc = res.rowcount
        if rc is not None and rc > 0:
            rows += rc
    db.commit()
    return rows


def backfill_employees_from_orphan_logs(db: Session) -> int:
    """Create Employee rows for attendance_logs.employee_code values with no employee yet."""
    correlated = exists(select(1).where(Employee.device_user_id == AttendanceLog.employee_code))
    stmt = (
        select(AttendanceLog.employee_code)
        .distinct()
        .where(~correlated)
        .where(AttendanceLog.employee_code != "")
        .where(AttendanceLog.employee_code.isnot(None))
    )
    codes = [str(c).strip() for c in db.execute(stmt).scalars().all() if c is not None and str(c).strip()]
    if not codes:
        return 0
    inserted = 0
    settings = get_settings()
    now = datetime.now(ZoneInfo("UTC"))
    for code in codes:
        res = db.execute(
            pg_insert(Employee)
            .values(
                employee_uuid=str(uuid4()),
                device_user_id=code,
                name=f"User {code}",
                department=None,
                shift_start=None,
                shift_end=None,
            )
            .on_conflict_do_nothing(index_elements=[Employee.device_user_id])
        )
        rc = res.rowcount
        if rc is not None and rc > 0:
            inserted += 1
    employees = db.execute(select(Employee).where(Employee.device_user_id.in_(codes))).scalars().all()
    for emp in employees:
        if not emp.employee_uuid:
            emp.employee_uuid = str(uuid4())
            db.flush()
        _ensure_active_mapping(
            db,
            employee_uuid=emp.employee_uuid,
            device_id=settings.zk_device_id,
            device_user_id=emp.device_user_id,
            effective_at=now,
        )
    db.commit()
    return inserted


def prune_recent_duplicate_logs(db: Session, *, settings: Settings, days: int | None = None) -> int:
    """Deprecated: attendance history is never physically deleted. Dedup happens at insert time."""
    _ = (db, settings, days)
    return 0


def run_device_sync(
    db: Session,
    device: DeviceService | None = None,
    settings: Settings | None = None,
    *,
    full_resync: bool = False,
) -> tuple[int, int, int]:
    """
    Fetch attendance from device, insert logs, backfill employees, rebuild sessions.

    Returns (device_row_count, newly_inserted_log_rows, placeholder_employees_created).
    """
    from app.services.device_command_service import wait_for_correction_commands_clear

    settings = settings or get_settings()
    if not wait_for_correction_commands_clear(db, settings.zk_device_id, settings=settings):
        logger.warning(
            "Deferring device sync: CORRECT_ATTENDANCE still active for device %s",
            settings.zk_device_id,
        )
        return 0, 0, 0
    device = device or DeviceService(settings=settings)
    floor = None if full_resync else _incremental_sync_floor(db, device_id=settings.zk_device_id, settings=settings)
    fetched_records = device.fetch_attendance()
    if floor is not None:
        fetched_records = [row for row in fetched_records if row.timestamp >= floor]
    records = _dedupe_device_records(fetched_records, settings=settings)
    n = insert_attendance_logs_idempotent(db, records, settings.zk_device_id)
    placeholders = backfill_employees_from_orphan_logs(db)

    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    lookback = settings.session_rebuild_lookback_days
    window_start = today - timedelta(days=lookback - 1)

    employees = {str(e.device_user_id): e for e in db.execute(select(Employee)).scalars().all()}
    affected: dict[tuple[int, date], None] = {}
    for row in records:
        day = _local_date(row.timestamp, tz)
        if not (window_start <= day <= today):
            continue
        emp = employees.get(row.user_id)
        if emp is not None:
            affected[(emp.id, day)] = None

    start_utc = datetime.combine(window_start, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    end_utc = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    for code, ts in db.execute(
        select(AttendanceLog.employee_code, AttendanceLog.timestamp).where(
            AttendanceLog.timestamp >= start_utc,
            AttendanceLog.timestamp < end_utc,
        )
    ).all():
        day = _local_date(ts, tz)
        emp = employees.get(str(code))
        if emp is not None:
            affected[(emp.id, day)] = None

    for employee_id, day in sorted(affected.keys()):
        rebuild_sessions_for_employee_date(
            db, employee_id=employee_id, local_date=day, settings=settings, commit=False
        )
    if affected:
        db.commit()

    try:
        from app.ai.cache.redis_cache import AIResponseCache

        cache = AIResponseCache(settings)
        cache.delete_prefix("ai:management:")
        cache.delete_prefix("ai:report:")
        cache.delete_prefix("ai:copilot:")
        cache.delete_prefix("ai:anomaly:")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI cache invalidation skipped: %s", exc)

    return len(fetched_records), n, placeholders


def run_user_sync(
    db: Session,
    device: DeviceService | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Fetch users from device and insert new employees."""
    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    users = device.fetch_users()
    inserted = sync_employees_from_device_users(db, users)
    return len(users), inserted


# Re-export for callers that still import from attendance_service
__all__ = [
    "backfill_employees_from_orphan_logs",
    "insert_attendance_logs_idempotent",
    "prune_recent_duplicate_logs",
    "rebuild_sessions_for_local_date",
    "run_device_sync",
    "run_user_sync",
    "sync_employees_from_device_users",
]
