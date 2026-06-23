"""User sync, attendance log sync, and session pairing logic."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_event import AttendanceEvent
from app.models.attendance_log import AttendanceLog
from app.models.attendance_sync_suppression import AttendanceSyncSuppression
from app.models.employee import Employee
from app.models.device_user_mapping import DeviceUserMapping
from app.services.attendance_helpers import (
    is_suppressed_timestamp as _is_suppressed_timestamp,
    local_date as _local_date,
    resolve_mapping_for_punch as _resolve_mapping_for_punch,
)
from app.services.device_service import DeviceAttendanceRecord, DeviceService, DeviceUser

logger = logging.getLogger(__name__)


def _incremental_sync_floor(db: Session, *, device_id: str, settings: Settings) -> datetime | None:
    """Use recent overlap window so incremental sync avoids reprocessing full history."""
    latest = db.execute(
        select(AttendanceEvent.timestamp)
        .where(AttendanceEvent.device_id == device_id)
        .order_by(AttendanceEvent.timestamp.desc())
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
    """
    Collapse noisy back-to-back duplicate punches produced by unstable device firmware.
    Keeps earliest record within (employee, punch_type, window) group.
    """
    window = timedelta(seconds=settings.duplicate_punch_window_seconds)
    if window.total_seconds() <= 0:
        return list(records)
    out: list[DeviceAttendanceRecord] = []
    last_seen: dict[tuple[str, int], datetime] = {}
    for row in sorted(records, key=lambda r: r.timestamp):
        key = (row.user_id, row.punch)
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
    """
    Upsert device users into employees with ON CONFLICT DO NOTHING on device_user_id.
    Returns number of rows attempted (not necessarily inserted).
    """
    affected = 0
    now = datetime.now(ZoneInfo("UTC"))
    settings = get_settings()
    for u in users:
        # Transition helper: old builds stored uid as numeric string.
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
        # psycopg may return -1 for "unknown" on upsert rowcount
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
    suppressed = 0
    for r in records:
        employee_code = r.user_id
        punch_type = str(r.punch)
        if _is_suppressed_timestamp(
            db, device_id=device_id, employee_code=employee_code, timestamp=r.timestamp, settings=settings
        ):
            suppressed += 1
            continue
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
    if suppressed:
        logger.info("Skipped suppressed device punches during sync: %s", suppressed)
    db.commit()
    return rows


def backfill_employees_from_orphan_logs(db: Session) -> int:
    """
    Create Employee rows for any attendance_logs.employee_code that has no matching employee yet.

    Punches are keyed by device user id in logs; if the HR user list was never synced or the id
    only appears in historical attendance, those people were omitted from daily summaries. This
    links orphan codes so every puncher appears in the app (placeholder name until metadata sync).
    """
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


def _insert_sync_suppressions_idempotent(
    db: Session,
    *,
    device_id: str,
    employee_code: str,
    timestamps: list[datetime],
    correction_id: int,
) -> None:
    """Record suppressed punch times; skip rows already suppressed (re-edit safe)."""
    seen: set[datetime] = set()
    for ts in timestamps:
        if ts in seen:
            continue
        seen.add(ts)
        stmt = (
            pg_insert(AttendanceSyncSuppression)
            .values(
                device_id=device_id,
                employee_code=employee_code,
                suppressed_timestamp=ts,
                reason="correction",
                correction_id=correction_id,
            )
            .on_conflict_do_nothing(constraint="uq_suppression_device_employee_ts")
        )
        db.execute(stmt)


def prune_recent_duplicate_logs(db: Session, *, settings: Settings, days: int | None = None) -> int:
    """Deprecated: attendance history is never physically deleted. Dedup happens at insert time."""
    _ = (db, settings, days)
    return 0


def rebuild_sessions_for_local_date(
    db: Session,
    target: date,
    settings: Settings | None = None,
    *,
    commit: bool = True,
    employee_ids: set[int] | None = None,
) -> int:
    """
    Recompute sessions for a local calendar day. When employee_ids is provided, only those
    employees are rebuilt; otherwise all employees with punches on that day are processed.
    """
    from app.services.attendance_effective_service import rebuild_sessions_for_local_date as _rebuild_all

    return _rebuild_all(db, target, settings=settings, commit=commit)


def run_device_sync(
    db: Session,
    device: DeviceService | None = None,
    settings: Settings | None = None,
    *,
    full_resync: bool = False,
) -> tuple[int, int, int]:
    """
    Fetch attendance from device, insert logs, backfill missing employees for any punch codes,
    rebuild sessions for a trailing window of local days.

    Returns (device_row_count, newly_inserted_log_rows, placeholder_employees_created).
    """
    from app.services.attendance_effective_service import (
        append_attendance_events_idempotent,
        rebuild_sessions_for_employee_date,
        sync_effective_punches_from_events,
    )

    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    floor = None if full_resync else _incremental_sync_floor(db, device_id=settings.zk_device_id, settings=settings)
    fetched_records = device.fetch_attendance()
    if floor is not None:
        fetched_records = [row for row in fetched_records if row.timestamp >= floor]
    records = _dedupe_device_records(fetched_records, settings=settings)
    batch_uuid = str(uuid4())
    n_events = append_attendance_events_idempotent(
        db, records, settings.zk_device_id, sync_batch_uuid=batch_uuid
    )
    n = insert_attendance_logs_idempotent(db, records, settings.zk_device_id)
    _ = n_events
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

    for employee_id, day in sorted(affected.keys()):
        emp = db.get(Employee, employee_id)
        if emp is None:
            continue
        sync_effective_punches_from_events(db, employee=emp, local_date=day, settings=settings, commit=False)
        rebuild_sessions_for_employee_date(
            db, employee_id=employee_id, local_date=day, settings=settings, commit=False
        )
    if affected:
        db.commit()

    # Keep AI summaries/reporting aligned with fresh attendance syncs.
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


def reimport_attendance_window(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    device: DeviceService | None = None,
    settings: Settings | None = None,
) -> tuple[int, list[datetime]]:
    """
    Append device punches for one employee/local day (never deletes attendance history).

    Returns (appended_event_count, device_timestamps_imported).
    """
    from app.services.attendance_effective_service import append_device_day_events

    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    tz = ZoneInfo(settings.timezone)
    start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))
    employee_code = str(employee.device_user_id)

    fetched = device.fetch_attendance()
    day_records: list[DeviceAttendanceRecord] = []
    for row in fetched:
        if row.user_id != employee_code:
            continue
        ts = row.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=tz)
        ts_utc = ts.astimezone(ZoneInfo("UTC"))
        if ts_utc < start_utc or ts_utc >= end_utc:
            continue
        day_records.append(
            DeviceAttendanceRecord(
                user_id=row.user_id,
                timestamp=ts_utc,
                punch=row.punch,
                status=row.status,
            )
        )

    imported_ts = append_device_day_events(
        db,
        employee=employee,
        local_date=local_date,
        device_records=day_records,
        device_id=settings.zk_device_id,
        source="device_verification",
    )

    for record in day_records:
        if _is_suppressed_timestamp(
            db,
            device_id=settings.zk_device_id,
            employee_code=employee_code,
            timestamp=record.timestamp,
            settings=settings,
        ):
            continue
        mapping = _resolve_mapping_for_punch(
            db,
            device_id=settings.zk_device_id,
            device_user_id=employee_code,
            at_time=record.timestamp,
        )
        stmt = (
            pg_insert(AttendanceLog)
            .values(
                employee_code=employee_code,
                timestamp=record.timestamp,
                device_id=settings.zk_device_id,
                employee_uuid=employee.employee_uuid,
                device_mapping_id=mapping.id if mapping else None,
                punch_type=str(record.punch),
                created_at=record.timestamp,
            )
            .on_conflict_do_nothing(constraint="uq_log_device_employee_ts")
        )
        db.execute(stmt)
    db.commit()
    return len(imported_ts), imported_ts


def run_user_sync(
    db: Session,
    device: DeviceService | None = None,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Fetch users from device and insert new employees (ON CONFLICT DO NOTHING)."""
    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    users = device.fetch_users()
    inserted = sync_employees_from_device_users(db, users)
    return len(users), inserted
