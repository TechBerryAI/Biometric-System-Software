"""User sync, attendance log sync, and session pairing logic."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_log import AttendanceLog
from app.models.attendance_session import AttendanceSession
from app.models.attendance_sync_suppression import AttendanceSyncSuppression
from app.models.device_user_mapping import DeviceUserMapping
from app.models.employee import Employee
from app.services.punch_classification import classify_punch
from app.services.device_service import DeviceAttendanceRecord, DeviceService, DeviceUser

logger = logging.getLogger(__name__)


def _is_suppressed_timestamp(
    db: Session,
    *,
    device_id: str,
    employee_code: str,
    timestamp: datetime,
) -> bool:
    row = db.execute(
        select(AttendanceSyncSuppression.id).where(
            AttendanceSyncSuppression.device_id == device_id,
            AttendanceSyncSuppression.employee_code == employee_code,
            AttendanceSyncSuppression.suppressed_timestamp == timestamp,
        ).limit(1)
    ).scalar_one_or_none()
    return row is not None


def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


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


def _resolve_mapping_for_punch(
    db: Session,
    *,
    device_id: str,
    device_user_id: str,
    at_time: datetime,
) -> DeviceUserMapping | None:
    return db.execute(
        select(DeviceUserMapping)
        .where(
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.device_user_id == device_user_id,
            DeviceUserMapping.valid_from <= at_time,
            or_(DeviceUserMapping.valid_to.is_(None), DeviceUserMapping.valid_to > at_time),
        )
        .order_by(DeviceUserMapping.valid_from.desc())
        .limit(1)
    ).scalar_one_or_none()


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
        if _is_suppressed_timestamp(db, device_id=device_id, employee_code=employee_code, timestamp=r.timestamp):
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


def prune_recent_duplicate_logs(db: Session, *, settings: Settings, days: int | None = None) -> int:
    """
    Remove near-duplicate punches (same employee/device/punch within duplicate window)
    in the recent sync horizon. Keeps earliest row and deletes later jitter duplicates.
    """
    window_seconds = settings.duplicate_punch_window_seconds
    if window_seconds <= 0:
        return 0
    horizon_days = days or settings.session_rebuild_lookback_days
    since = datetime.now(ZoneInfo("UTC")) - timedelta(days=horizon_days)
    rows = list(
        db.execute(
            select(AttendanceLog)
            .where(AttendanceLog.timestamp >= since)
            .order_by(
                AttendanceLog.device_id.asc(),
                AttendanceLog.employee_code.asc(),
                AttendanceLog.punch_type.asc(),
                AttendanceLog.timestamp.asc(),
                AttendanceLog.id.asc(),
            )
        ).scalars().all()
    )
    to_delete: list[int] = []
    last_seen: dict[tuple[str, str, str, str | None], datetime] = {}
    for row in rows:
        key = (row.device_id, row.employee_code, row.punch_type, row.employee_uuid)
        prev = last_seen.get(key)
        if prev is not None and (row.timestamp - prev).total_seconds() <= window_seconds:
            to_delete.append(row.id)
            continue
        last_seen[key] = row.timestamp
    if not to_delete:
        return 0
    deleted = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.id.in_(to_delete))
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info("Pruned duplicate attendance logs: %s", deleted)
    return int(deleted or 0)


def _pair_logs_for_day(
    logs: list[AttendanceLog],
    _tz: ZoneInfo,
    *,
    duplicate_window_seconds: int,
) -> list[tuple[AttendanceLog, AttendanceLog | None, str]]:
    """
    Pair IN/OUT for one employee for one local calendar day.
    Returns list of (check_in_log, check_out_log_or_none, status).
    """
    logs_sorted = sorted(logs, key=lambda x: x.timestamp)
    sessions: list[tuple[AttendanceLog, AttendanceLog | None, str]] = []
    pending_in: AttendanceLog | None = None
    next_expects_in = True
    duplicate_window = timedelta(seconds=duplicate_window_seconds)

    for log in logs_sorted:
        cls = classify_punch(log.punch_type)
        if cls is True:
            if pending_in is not None and duplicate_window.total_seconds() > 0:
                if log.timestamp - pending_in.timestamp <= duplicate_window:
                    # Ignore rapid duplicate IN generated by some firmware.
                    continue
            if pending_in is not None:
                sessions.append((pending_in, None, "missing_check_out"))
            pending_in = log
            next_expects_in = False
        elif cls is False:
            if pending_in is None:
                continue
            if log.timestamp <= pending_in.timestamp:
                continue
            if duplicate_window.total_seconds() > 0 and log.timestamp - pending_in.timestamp <= duplicate_window:
                # Ignore immediate IN->OUT jitter that does not represent a real session.
                continue
            sessions.append((pending_in, log, "complete"))
            pending_in = None
            next_expects_in = True
        else:
            if next_expects_in:
                if pending_in is not None:
                    sessions.append((pending_in, None, "missing_check_out"))
                pending_in = log
                next_expects_in = False
            else:
                if pending_in is None:
                    next_expects_in = True
                    continue
                if log.timestamp <= pending_in.timestamp:
                    continue
                sessions.append((pending_in, log, "complete"))
                pending_in = None
                next_expects_in = True

    if pending_in is not None:
        sessions.append((pending_in, None, "missing_check_out"))

    return sessions


def rebuild_sessions_for_local_date(
    db: Session,
    target: date,
    settings: Settings | None = None,
    *,
    commit: bool = True,
) -> int:
    """
    Recompute AttendanceSession rows for all employees for a given local calendar day.
    Deletes existing sessions whose check_in falls on that local date, then rebuilds from logs.
    """
    settings = settings or get_settings()
    tz = ZoneInfo(settings.timezone)

    start_local = datetime.combine(target, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))

    db.execute(
        delete(AttendanceSession).where(
            and_(
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
        )
    )

    log_rows = db.execute(
        select(AttendanceLog).where(
            AttendanceLog.timestamp >= start_utc,
            AttendanceLog.timestamp < end_utc,
        )
    ).scalars().all()

    by_employee_day: dict[tuple[int, date], list[AttendanceLog]] = defaultdict(list)
    employees = db.execute(select(Employee)).scalars().all()
    code_to_employee: dict[str, Employee] = {str(e.device_user_id): e for e in employees}
    uuid_to_employee: dict[str, Employee] = {e.employee_uuid: e for e in employees if e.employee_uuid}
    for lg in log_rows:
        d = _local_date(lg.timestamp, tz)
        if d == target:
            emp: Employee | None = None
            if lg.employee_uuid:
                emp = uuid_to_employee.get(lg.employee_uuid)
            if emp is None:
                emp = code_to_employee.get(lg.employee_code)
            if emp is None:
                continue
            by_employee_day[(emp.id, d)].append(lg)

    created = 0
    employee_by_id: dict[int, Employee] = {e.id: e for e in employees}
    for (employee_id, _day), day_logs in by_employee_day.items():
        emp = employee_by_id.get(employee_id)
        if emp is None:
            continue
        pairs = _pair_logs_for_day(
            day_logs,
            tz,
            duplicate_window_seconds=settings.duplicate_punch_window_seconds,
        )
        for cin_log, cout_log, status in pairs:
            check_in = cin_log.timestamp
            check_out = cout_log.timestamp if cout_log else None
            work_min: int | None = None
            if check_out and check_out > check_in:
                work_min = int((check_out - check_in).total_seconds() // 60)

            db.add(
                AttendanceSession(
                    employee_id=emp.id,
                    check_in=check_in,
                    check_out=check_out,
                    work_duration=work_min,
                    status=status,
                )
            )
            created += 1

    if commit:
        db.commit()
    return created


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
    settings = settings or get_settings()
    device = device or DeviceService(settings=settings)
    floor = None if full_resync else _incremental_sync_floor(db, device_id=settings.zk_device_id, settings=settings)
    fetched_records = device.fetch_attendance()
    if floor is not None:
        fetched_records = [row for row in fetched_records if row.timestamp >= floor]
    records = _dedupe_device_records(fetched_records, settings=settings)
    n = insert_attendance_logs_idempotent(db, records, settings.zk_device_id)
    _ = prune_recent_duplicate_logs(db, settings=settings)
    placeholders = backfill_employees_from_orphan_logs(db)

    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    lookback = settings.session_rebuild_lookback_days
    window_start = today - timedelta(days=lookback - 1)
    affected_dates = sorted(
        {
            _local_date(row.timestamp, tz)
            for row in records
            if window_start <= _local_date(row.timestamp, tz) <= today
        }
    )
    if placeholders > 0:
        orphan_dates = sorted(
            {
                _local_date(row.timestamp, tz)
                for row in records
                if window_start <= _local_date(row.timestamp, tz) <= today
            }
        )
        affected_dates = sorted(set(affected_dates) | set(orphan_dates))
    if not affected_dates:
        affected_dates = [today]
    for day in affected_dates:
        rebuild_sessions_for_local_date(db, day, settings=settings)

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
