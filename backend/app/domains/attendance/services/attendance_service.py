"""User sync, attendance log sync, and session rebuild."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.employees.models.employee import Employee
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.attendance.services.attendance_helpers import (
    local_date as _local_date,
    rebuild_sessions_for_employee_date,
    rebuild_sessions_for_local_date,
    resolve_mapping_for_punch as _resolve_mapping_for_punch,
)
from app.domains.devices.services.device_service import DeviceAttendanceRecord, DeviceService, DeviceUser
from app.domains.employees.services.employee_offboard_service import enqueue_delete_user_command
from app.domains.attendance.services.punch_classification import device_attendance_punch_type

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeviceSyncResult:
    """Outcome of a single attendance pull + insert cycle."""

    fetched: int
    inserted: int
    placeholders: int
    skipped_corrected_punches: int = 0
    punches_missing_after_insert: int = 0
    skipped_reason: str | None = None


class AttendanceFetchSource(Protocol):
    """Anything that can supply attendance rows (pull DeviceService or PushConnector)."""

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]: ...


class UserFetchSource(Protocol):
    """Anything that can supply device users."""

    def fetch_users(self) -> list[DeviceUser]: ...


class MergedAttendanceSource:
    """Merge pull + push buffer attendance; exact dedupe happens in run_device_sync."""

    def __init__(self, *sources: AttendanceFetchSource) -> None:
        self._sources = sources

    def fetch_attendance(self) -> list[DeviceAttendanceRecord]:
        out: list[DeviceAttendanceRecord] = []
        for source in self._sources:
            out.extend(source.fetch_attendance())
        return out


class MergedUserSource:
    """Merge pull + push buffer users."""

    def __init__(self, *sources: UserFetchSource) -> None:
        self._sources = sources

    def fetch_users(self) -> list[DeviceUser]:
        out: list[DeviceUser] = []
        for source in self._sources:
            out.extend(source.fetch_users())
        return out



def _incremental_sync_floor(db: Session, *, device_id: str, settings: Settings) -> datetime | None:
    """Use recent overlap window so incremental sync avoids reprocessing full history.

    Only considers logs for this device_id. If this device has no rows yet, returns None
    so the full fetch is imported (never fall back to another device's latest timestamp).
    """
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
    settings: Settings | None = None,
) -> list[DeviceAttendanceRecord]:
    """Collapse exact duplicates within a single fetch batch (same user/ts/status/punch).

    Time-window near-dup filtering is intentionally not applied here — every distinct
    device event must reach storage. Display/session pairing may still collapse near
    scans via DUPLICATE_PUNCH_WINDOW_SECONDS.
    """
    del settings  # reserved for callers that still pass settings=
    seen: set[tuple[str, datetime, int, int]] = set()
    out: list[DeviceAttendanceRecord] = []
    for row in sorted(records, key=lambda r: r.timestamp):
        key = (row.user_id, row.timestamp, row.status, row.punch)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _resolve_mapping_with_legacy_fallback(
    db: Session,
    *,
    device_id: str,
    device_user_id: str,
    at_time: datetime,
    canonical_device_id: str,
):
    """Prefer mapping for the physical device; fall back to canonical id for legacy rows."""
    mapping = _resolve_mapping_for_punch(
        db,
        device_id=device_id,
        device_user_id=device_user_id,
        at_time=at_time,
    )
    if mapping is not None:
        return mapping
    if device_id != canonical_device_id:
        return _resolve_mapping_for_punch(
            db,
            device_id=canonical_device_id,
            device_user_id=device_user_id,
            at_time=at_time,
        )
    return None


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


def sync_employees_from_device_users(
    db: Session, users: Sequence[DeviceUser], *, device_id: str | None = None
) -> int:
    """Upsert device users into employees. Returns number of rows affected."""
    affected = 0
    now = datetime.now(ZoneInfo("UTC"))
    settings = get_settings()
    resolved_device_id = device_id or settings.zk_device_id
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
                    device_id=resolved_device_id,
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
            device_id=resolved_device_id,
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
    """Append-only insert of raw logs. Never updates or deletes existing rows.

    Exact replays are ignored via unique
    (device_id, employee_code, timestamp, punch_type) → ON CONFLICT DO NOTHING.

    Time-window near-duplicates are NOT skipped at storage time — every distinct
    device event is kept. Display/session pairing may still collapse near scans.

    Prepared rows are inserted in chunks (ATTENDANCE_BULK_INSERT_CHUNK_SIZE)
    via a single multi-VALUES INSERT per chunk for throughput.
    """
    rows = 0
    settings = get_settings()
    stamp_device_id = device_id or settings.zk_device_id
    canonical_device_id = settings.zk_device_id
    prepared: list[dict] = []
    # Exact keys already prepared in this batch (same as unique constraint).
    batch_seen: set[tuple[str, datetime, str]] = set()

    for r in records:
        employee_code = r.user_id
        punch_type = device_attendance_punch_type(status=r.status, punch=r.punch)
        batch_key = (employee_code, r.timestamp, punch_type)
        if batch_key in batch_seen:
            continue
        batch_seen.add(batch_key)
        mapping = _resolve_mapping_with_legacy_fallback(
            db,
            device_id=stamp_device_id,
            device_user_id=employee_code,
            at_time=r.timestamp,
            canonical_device_id=canonical_device_id,
        )
        prepared.append(
            {
                "employee_code": employee_code,
                "timestamp": r.timestamp,
                "device_id": stamp_device_id,
                "employee_uuid": mapping.employee_uuid if mapping else None,
                "device_mapping_id": mapping.id if mapping else None,
                "punch_type": punch_type,
            }
        )

    chunk_size = settings.attendance_bulk_insert_chunk_size
    for i in range(0, len(prepared), chunk_size):
        chunk = prepared[i : i + chunk_size]
        if not chunk:
            continue
        stmt = (
            pg_insert(AttendanceLog)
            .values(chunk)
            .on_conflict_do_nothing(
                index_elements=["device_id", "employee_code", "timestamp", "punch_type"]
            )
            .returning(AttendanceLog.id)
        )
        res = db.execute(stmt)
        rows += len(res.scalars().all())
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


def _aware_timestamp(ts: datetime, *, tz: ZoneInfo) -> datetime:
    if ts.tzinfo is not None:
        return ts
    return ts.replace(tzinfo=tz)


def _record_epoch_key(record: DeviceAttendanceRecord, punch_type: str, *, tz: ZoneInfo) -> tuple[str, int, str]:
    ts = record.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=tz)
    return (str(record.user_id).strip(), int(ts.timestamp()), punch_type)


def _naive_epoch_candidates(ts: datetime, *, tz: ZoneInfo) -> set[int]:
    """SQLite may persist either UTC or local wall as naive; accept both interpretations."""
    if ts.tzinfo is not None:
        return {int(ts.timestamp())}
    return {
        int(ts.replace(tzinfo=ZoneInfo("UTC")).timestamp()),
        int(ts.replace(tzinfo=tz).timestamp()),
    }


def count_fetched_missing_in_db(
    db: Session,
    records: Sequence[DeviceAttendanceRecord],
    device_id: str,
) -> int:
    """How many fetched device punches are still absent from attendance_logs."""
    if not records:
        return 0
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    keys = {
        _record_epoch_key(
            row,
            device_attendance_punch_type(status=row.status, punch=row.punch),
            tz=tz,
        )
        for row in records
    }
    codes = {k[0] for k in keys}
    aware_bounds = [
        row.timestamp if row.timestamp.tzinfo is not None else row.timestamp.replace(tzinfo=tz)
        for row in records
    ]
    min_ts = min(aware_bounds)
    max_ts = max(aware_bounds)
    # Wide pad: naive SQLite reinterpretation can shift by timezone offset.
    pad = timedelta(hours=14)
    db_pairs: list[tuple[str, set[int], str]] = []
    for code, ts, punch_type in db.execute(
        select(AttendanceLog.employee_code, AttendanceLog.timestamp, AttendanceLog.punch_type).where(
            AttendanceLog.device_id == device_id,
            AttendanceLog.employee_code.in_(codes),
            AttendanceLog.timestamp >= min_ts - pad,
            AttendanceLog.timestamp <= max_ts + pad,
        )
    ).all():
        db_pairs.append((str(code).strip(), _naive_epoch_candidates(ts, tz=tz), str(punch_type)))

    missing = 0
    for code, epoch, punch_type in keys:
        if not any(
            code == db_code and punch_type == db_punch and epoch in epochs
            for db_code, epochs, db_punch in db_pairs
        ):
            missing += 1
    return missing


def run_device_sync(
    db: Session,
    device: AttendanceFetchSource | None = None,
    settings: Settings | None = None,
    *,
    full_resync: bool = False,
    device_id: str | None = None,
) -> tuple[int, int, int]:
    """
    Fetch attendance from device, insert logs, backfill employees, rebuild sessions.

    Returns (device_row_count, newly_inserted_log_rows, placeholder_employees_created).
    Prefer ``run_device_sync_detailed`` when skip/reconcile metrics are needed.
    """
    result = run_device_sync_detailed(
        db, device=device, settings=settings, full_resync=full_resync, device_id=device_id
    )
    return result.fetched, result.inserted, result.placeholders


def run_device_sync_detailed(
    db: Session,
    device: AttendanceFetchSource | None = None,
    settings: Settings | None = None,
    *,
    full_resync: bool = False,
    device_id: str | None = None,
) -> DeviceSyncResult:
    """
    Fetch attendance from device, insert logs, backfill employees, rebuild sessions.

    Mid-day attendance corrections only block punches at or before protect_until so
    later genuine punches (evening OUT) still sync.
    """
    from app.domains.attendance.services.attendance_correction_service import (
        is_punch_blocked_by_correction,
        load_corrected_day_guards,
    )
    from app.domains.devices.services.device_command_service import wait_for_correction_commands_clear

    settings = settings or get_settings()
    resolved_device_id = device_id or settings.zk_device_id
    if not wait_for_correction_commands_clear(db, resolved_device_id, settings=settings):
        logger.warning(
            "Deferring device sync: CORRECT_ATTENDANCE still active for device %s",
            resolved_device_id,
        )
        return DeviceSyncResult(
            fetched=0,
            inserted=0,
            placeholders=0,
            skipped_reason="correction_active",
        )
    device = device or DeviceService(settings=settings)
    floor = None if full_resync else _incremental_sync_floor(db, device_id=resolved_device_id, settings=settings)
    fetched_records = device.fetch_attendance()
    fetched_count = len(fetched_records)
    if floor is not None:
        fetched_records = [row for row in fetched_records if row.timestamp >= floor]
    records = _dedupe_device_records(fetched_records)

    tz = ZoneInfo(settings.timezone)
    guards = load_corrected_day_guards(db, device_id=resolved_device_id)
    skipped_corrected = 0
    if guards:
        kept: list[DeviceAttendanceRecord] = []
        for row in records:
            day = _local_date(row.timestamp, tz)
            if is_punch_blocked_by_correction(
                user_id=str(row.user_id).strip(),
                timestamp=row.timestamp,
                local_day=day,
                guards=guards,
            ):
                skipped_corrected += 1
                continue
            kept.append(row)
        if skipped_corrected:
            logger.info(
                "Sync skipped %s device punch(es) on corrected employee-days (post-correction punches kept)",
                skipped_corrected,
            )
        records = kept

    n = insert_attendance_logs_idempotent(db, records, resolved_device_id)
    missing_after = count_fetched_missing_in_db(db, records, resolved_device_id)
    if missing_after:
        logger.error(
            "Punch reconciliation failed for device %s: %s fetched punches still missing after insert",
            resolved_device_id,
            missing_after,
        )
    placeholders = backfill_employees_from_orphan_logs(db)

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

    return DeviceSyncResult(
        fetched=fetched_count,
        inserted=n,
        placeholders=placeholders,
        skipped_corrected_punches=skipped_corrected,
        punches_missing_after_insert=missing_after,
    )


def run_user_sync(
    db: Session,
    device: UserFetchSource | None = None,
    settings: Settings | None = None,
    *,
    device_id: str | None = None,
) -> tuple[int, int]:
    """Fetch users from device and insert new employees."""
    settings = settings or get_settings()
    resolved_device_id = device_id or settings.zk_device_id
    device = device or DeviceService(settings=settings)
    users = device.fetch_users()
    inserted = sync_employees_from_device_users(db, users, device_id=resolved_device_id)
    return len(users), inserted


# Re-export for callers that still import from attendance_service
__all__ = [
    "DeviceSyncResult",
    "MergedAttendanceSource",
    "MergedUserSource",
    "backfill_employees_from_orphan_logs",
    "count_fetched_missing_in_db",
    "insert_attendance_logs_idempotent",
    "prune_recent_duplicate_logs",
    "rebuild_sessions_for_local_date",
    "run_device_sync",
    "run_device_sync_detailed",
    "run_user_sync",
    "sync_employees_from_device_users",
]
