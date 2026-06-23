"""Effective attendance layer: derived punches and employee-scoped session rebuild."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_correction import AttendanceCorrection
from app.models.attendance_effective_punch import AttendanceEffectivePunch
from app.models.attendance_event import AttendanceEvent
from app.models.attendance_session import AttendanceSession
from app.models.attendance_log import AttendanceLog
from app.models.attendance_sync_suppression import AttendanceSyncSuppression
from app.models.employee import Employee
from app.services.attendance_helpers import (
    is_suppressed_timestamp,
    pair_logs_for_day,
    resolve_mapping_for_punch,
)
from app.services.device_attlog_protocol import _ts_match
from app.services.device_service import DeviceAttendanceRecord
from app.services.punch_classification import (
    classify_punch,
    device_attendance_punch_type,
    is_legacy_verify_punch_type,
    resolve_punch_types_for_day,
    summarize_day_punches,
)

logger = logging.getLogger(__name__)

PUNCH_IN = "0"
PUNCH_OUT = "1"

_APPLIED_CORRECTION_STATUSES = frozenset({"applied", "applied_db_only"})


@dataclass(frozen=True, slots=True)
class DayAttendanceSnapshot:
    local_date: date
    first_check_in: datetime | None
    last_check_out: datetime | None
    log_ids: list[int]
    log_timestamps: list[datetime]


def _day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


@dataclass(frozen=True, slots=True)
class _PunchRow:
    timestamp: datetime
    punch_type: str


def _dedupe_punch_rows(
    punches: Sequence[_PunchRow],
    *,
    employee_code: str,
    settings: Settings,
) -> list[_PunchRow]:
    """Collapse near-duplicate punches (double-tap) without dropping distinct check-in/out pairs."""
    window = timedelta(seconds=settings.duplicate_punch_window_seconds)
    if window.total_seconds() <= 0:
        return list(punches)
    out: list[_PunchRow] = []
    last_seen: dict[tuple[str, str], datetime] = {}
    for row in sorted(punches, key=lambda p: p.timestamp):
        key = (row.punch_type, employee_code)
        prev = last_seen.get(key)
        if prev is not None and row.timestamp - prev <= window:
            continue
        out.append(row)
        last_seen[key] = row.timestamp
    return out


def _merge_punch_rows(events: Sequence[AttendanceEvent], logs: Sequence[AttendanceLog]) -> list[_PunchRow]:
    """Union events and logs; merge only exact near-duplicate timestamps (±2s), never drop distinct punches."""
    candidates: list[_PunchRow] = [
        _PunchRow(timestamp=row.timestamp, punch_type=str(row.punch_type))
        for row in list(events) + list(logs)
    ]
    candidates.sort(key=lambda p: p.timestamp)
    merged: list[_PunchRow] = []
    for candidate in candidates:
        replaced = False
        for idx, existing in enumerate(merged):
            if abs((candidate.timestamp - existing.timestamp).total_seconds()) > 2:
                continue
            if is_legacy_verify_punch_type(existing.punch_type) and not is_legacy_verify_punch_type(
                candidate.punch_type
            ):
                merged[idx] = candidate
            elif classify_punch(candidate.punch_type) is not None and classify_punch(existing.punch_type) is None:
                merged[idx] = candidate
            replaced = True
            break
        if not replaced:
            merged.append(candidate)
    return merged


def _logs_for_employee_day(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings,
    apply_suppression: bool = False,
) -> list[AttendanceLog]:
    start_utc, end_utc = _day_bounds_utc(local_date, settings.timezone)
    employee_code = str(employee.device_user_id)
    q = select(AttendanceLog).where(
        AttendanceLog.timestamp >= start_utc,
        AttendanceLog.timestamp < end_utc,
        AttendanceLog.employee_code == employee_code,
    )
    if employee.employee_uuid:
        q = q.where(
            (AttendanceLog.employee_uuid == employee.employee_uuid) | (AttendanceLog.employee_uuid.is_(None))
        )
    rows = list(db.execute(q.order_by(AttendanceLog.timestamp)).scalars().all())
    filtered: list[AttendanceLog] = []
    for log in rows:
        if apply_suppression and is_suppressed_timestamp(
            db,
            device_id=log.device_id,
            employee_code=log.employee_code,
            timestamp=log.timestamp,
            settings=settings,
        ):
            continue
        filtered.append(log)
    return filtered


def _latest_applied_correction(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
) -> AttendanceCorrection | None:
    return db.execute(
        select(AttendanceCorrection)
        .where(
            AttendanceCorrection.employee_id == employee_id,
            AttendanceCorrection.local_date == local_date,
            AttendanceCorrection.status.in_(_APPLIED_CORRECTION_STATUSES),
            AttendanceCorrection.new_check_in.is_not(None),
        )
        .order_by(AttendanceCorrection.applied_at.desc().nullslast(), AttendanceCorrection.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _punches_for_employee_day(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings,
    apply_suppression: bool = False,
) -> list[_PunchRow]:
    """Merged, deduped punch rows for one employee-day from events and logs."""
    start_utc, end_utc = _day_bounds_utc(local_date, settings.timezone)
    employee_code = str(employee.device_user_id)
    q = select(AttendanceEvent).where(
        AttendanceEvent.timestamp >= start_utc,
        AttendanceEvent.timestamp < end_utc,
        AttendanceEvent.employee_code == employee_code,
    )
    if employee.employee_uuid:
        q = q.where(
            (AttendanceEvent.employee_uuid == employee.employee_uuid) | (AttendanceEvent.employee_uuid.is_(None))
        )
    events_raw = list(db.execute(q.order_by(AttendanceEvent.timestamp)).scalars().all())
    events: list[AttendanceEvent] = []
    for ev in events_raw:
        if apply_suppression and is_suppressed_timestamp(
            db,
            device_id=ev.device_id,
            employee_code=ev.employee_code,
            timestamp=ev.timestamp,
            settings=settings,
        ):
            continue
        events.append(ev)
    logs = _logs_for_employee_day(
        db, employee=employee, local_date=local_date, settings=settings, apply_suppression=apply_suppression
    )
    merged = _merge_punch_rows(events, logs)
    return _dedupe_punch_rows(merged, employee_code=employee_code, settings=settings)


def repair_punch_types_from_device_records(
    db: Session,
    records: Sequence[DeviceAttendanceRecord],
    device_id: str,
) -> int:
    """
    Fix legacy rows that stored verify mode instead of check direction.

    Runs on every device sync so existing misclassified punches are corrected in place.
    """
    repaired = 0
    match_window = timedelta(seconds=2)
    for r in records:
        canonical = device_attendance_punch_type(status=r.status, punch=r.punch)
        employee_code = r.user_id
        for model in (AttendanceEvent, AttendanceLog):
            row = db.execute(
                select(model).where(
                    model.device_id == device_id,
                    model.employee_code == employee_code,
                    model.timestamp >= r.timestamp - match_window,
                    model.timestamp <= r.timestamp + match_window,
                ).limit(1)
            ).scalar_one_or_none()
            if row is None:
                continue
            stored = str(row.punch_type)
            if stored == canonical:
                continue
            if is_legacy_verify_punch_type(stored) or classify_punch(stored) is None or stored != canonical:
                row.punch_type = canonical
                repaired += 1
    if repaired:
        db.commit()
    return repaired


def sync_effective_punches_from_events(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
    commit: bool = True,
) -> int:
    """Rebuild active effective punches for one employee-day from raw events (non-correction path)."""
    settings = settings or get_settings()
    punches = _punches_for_employee_day(
        db, employee=employee, local_date=local_date, settings=settings, apply_suppression=False
    )

    db.execute(
        update(AttendanceEffectivePunch)
        .where(
            AttendanceEffectivePunch.employee_id == employee.id,
            AttendanceEffectivePunch.local_date == local_date,
            AttendanceEffectivePunch.is_active.is_(True),
            AttendanceEffectivePunch.correction_uuid.is_(None),
        )
        .values(is_active=False)
    )

    inserted = 0
    resolved = resolve_punch_types_for_day(
        [p.punch_type for p in punches],
        [p.timestamp for p in punches],
        tz_name=settings.timezone,
    )
    for punch, direction in zip(punches, resolved, strict=True):
        db.add(
            AttendanceEffectivePunch(
                employee_id=employee.id,
                local_date=local_date,
                punch_type=direction,
                timestamp=punch.timestamp,
                source="derived",
                correction_uuid=None,
                is_active=True,
            )
        )
        inserted += 1
    if commit:
        db.commit()
    return inserted


def apply_correction_to_effective_punches(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    new_check_in: datetime,
    new_check_out: datetime | None,
    correction_uuid: str,
    settings: Settings | None = None,
    commit: bool = True,
) -> int:
    """Deactivate prior effective punches and insert corrected times (never deletes rows)."""
    settings = settings or get_settings()
    db.execute(
        update(AttendanceEffectivePunch)
        .where(
            AttendanceEffectivePunch.employee_id == employee.id,
            AttendanceEffectivePunch.local_date == local_date,
            AttendanceEffectivePunch.is_active.is_(True),
        )
        .values(is_active=False)
    )
    inserted = 0
    for punch_type, ts in ((PUNCH_IN, new_check_in), (PUNCH_OUT, new_check_out)):
        if ts is None:
            continue
        db.add(
            AttendanceEffectivePunch(
                employee_id=employee.id,
                local_date=local_date,
                punch_type=punch_type,
                timestamp=ts,
                source="correction",
                correction_uuid=correction_uuid,
                is_active=True,
            )
        )
        inserted += 1
    if commit:
        db.commit()
    return inserted


def _effective_needs_correction_reapply(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
    correction: AttendanceCorrection,
) -> bool:
    active = load_active_effective_punches(db, employee_id=employee_id, local_date=local_date)
    if not active:
        return True
    return not any(p.correction_uuid == correction.correction_uuid for p in active)


def _correction_covers_day_better_than_raw(
    correction: AttendanceCorrection,
    raw_punches: Sequence[_PunchRow],
    *,
    tz_name: str,
) -> bool:
    """
    Prefer an applied correction only when raw punches are missing or clearly less complete.

    Avoids a partial manual correction (e.g. morning-only tweak) hiding a full device day.
    """
    if not raw_punches:
        return True
    raw_in, raw_out, raw_min = summarize_day_punches(raw_punches, tz_name=tz_name)
    if raw_in is None and raw_out is None:
        return True
    if correction.new_check_in is None:
        return False
    corr_out = correction.new_check_out
    if corr_out is None:
        return raw_in is None and raw_out is None
    if raw_in is None or raw_out is None:
        return True
    corr_min = int((corr_out - correction.new_check_in).total_seconds() // 60)
    if raw_min is None:
        return True
    # Raw device day is substantially longer — keep full punches instead of a short correction.
    if raw_min > corr_min + 60:
        return False
    return True


def ensure_effective_punches_for_day(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
    commit: bool = True,
) -> None:
    """
    Guarantee the effective layer reflects the best-known truth for one employee-day.

    Applied corrections take priority; otherwise rebuild from full raw events + logs
    (correction suppressions apply only during device re-sync, not display).
    """
    settings = settings or get_settings()
    raw_punches = _punches_for_employee_day(
        db, employee=employee, local_date=local_date, settings=settings, apply_suppression=False
    )
    correction = _latest_applied_correction(db, employee_id=employee.id, local_date=local_date)
    if (
        correction is not None
        and correction.new_check_in is not None
        and _correction_covers_day_better_than_raw(correction, raw_punches, tz_name=settings.timezone)
    ):
        if _effective_needs_correction_reapply(
            db, employee_id=employee.id, local_date=local_date, correction=correction
        ):
            apply_correction_to_effective_punches(
                db,
                employee=employee,
                local_date=local_date,
                new_check_in=correction.new_check_in,
                new_check_out=correction.new_check_out,
                correction_uuid=correction.correction_uuid,
                settings=settings,
                commit=False,
            )
    else:
        sync_effective_punches_from_events(
            db, employee=employee, local_date=local_date, settings=settings, commit=False
        )
    rebuild_sessions_for_employee_date(
        db, employee_id=employee.id, local_date=local_date, settings=settings, commit=False
    )
    if commit:
        db.commit()


def summarize_employee_day_from_events(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
) -> tuple[datetime | None, datetime | None, int | None, int]:
    """Derive day IN/OUT/work minutes from the effective attendance layer."""
    settings = settings or get_settings()
    effective = load_active_effective_punches(db, employee_id=employee.id, local_date=local_date)
    if effective:
        first_in, last_out, total_min = summarize_day_punches(effective, tz_name=settings.timezone)
        return first_in, last_out, total_min, len(effective)

    punches = _punches_for_employee_day(
        db, employee=employee, local_date=local_date, settings=settings, apply_suppression=False
    )
    if punches:
        first_in, last_out, total_min = summarize_day_punches(punches, tz_name=settings.timezone)
        return first_in, last_out, total_min, len(punches)

    correction = _latest_applied_correction(db, employee_id=employee.id, local_date=local_date)
    if correction is not None and correction.new_check_in is not None:
        first_in = correction.new_check_in
        last_out = correction.new_check_out
        total_min: int | None = None
        if last_out is not None and last_out > first_in:
            total_min = int((last_out - first_in).total_seconds() // 60)
        punch_count = 1 + (1 if last_out is not None else 0)
        return first_in, last_out, total_min, punch_count

    return None, None, None, 0


def load_active_effective_punches(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
) -> list[AttendanceEffectivePunch]:
    return list(
        db.execute(
            select(AttendanceEffectivePunch)
            .where(
                AttendanceEffectivePunch.employee_id == employee_id,
                AttendanceEffectivePunch.local_date == local_date,
                AttendanceEffectivePunch.is_active.is_(True),
            )
            .order_by(AttendanceEffectivePunch.timestamp)
        ).scalars().all()
    )


def rebuild_sessions_for_employee_date(
    db: Session,
    *,
    employee_id: int,
    local_date: date,
    settings: Settings | None = None,
    commit: bool = True,
) -> int:
    """Recompute sessions for a single employee on a single local date from effective punches."""
    settings = settings or get_settings()
    tz = ZoneInfo(settings.timezone)
    start_utc, end_utc = _day_bounds_utc(local_date, settings.timezone)

    db.execute(
        delete(AttendanceSession).where(
            and_(
                AttendanceSession.employee_id == employee_id,
                AttendanceSession.check_in >= start_utc,
                AttendanceSession.check_in < end_utc,
            )
        )
    )

    effective = load_active_effective_punches(db, employee_id=employee_id, local_date=local_date)
    if not effective:
        if commit:
            db.commit()
        return 0

    pseudo_logs: list[AttendanceEvent] = []
    for punch in effective:
        pseudo_logs.append(
            AttendanceEvent(
                id=punch.id,
                event_uuid=str(uuid4()),
                employee_code="",
                timestamp=punch.timestamp,
                device_id="",
                punch_type=punch.punch_type,
                source=punch.source,
            )
        )

    pairs = pair_logs_for_day(
        pseudo_logs,  # type: ignore[arg-type]
        tz,
        duplicate_window_seconds=settings.duplicate_punch_window_seconds,
    )
    created = 0
    for cin_log, cout_log, status in pairs:
        check_in = cin_log.timestamp
        check_out = cout_log.timestamp if cout_log else None
        work_min: int | None = None
        if check_out and check_out > check_in:
            work_min = int((check_out - check_in).total_seconds() // 60)
        db.add(
            AttendanceSession(
                employee_id=employee_id,
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


def rebuild_sessions_for_local_date(
    db: Session,
    target: date,
    settings: Settings | None = None,
    *,
    commit: bool = True,
) -> int:
    """Rebuild sessions for all employees on a date (sync path only)."""
    settings = settings or get_settings()
    employees = list(db.execute(select(Employee)).scalars().all())
    total = 0
    for emp in employees:
        sync_effective_punches_from_events(db, employee=emp, local_date=target, settings=settings, commit=False)
        total += rebuild_sessions_for_employee_date(
            db, employee_id=emp.id, local_date=target, settings=settings, commit=False
        )
    if commit:
        db.commit()
    return total


def append_attendance_events_idempotent(
    db: Session,
    records: Sequence[DeviceAttendanceRecord],
    device_id: str,
    *,
    source: str = "device_sync",
    sync_batch_uuid: str | None = None,
) -> int:
    """Append raw device punches to attendance_events (never update or delete)."""
    rows = 0
    settings = get_settings()
    duplicate_window = timedelta(seconds=settings.duplicate_punch_window_seconds)

    for r in records:
        employee_code = r.user_id
        punch_type = device_attendance_punch_type(status=r.status, punch=r.punch)
        if is_suppressed_timestamp(
            db, device_id=device_id, employee_code=employee_code, timestamp=r.timestamp, settings=settings
        ):
            continue
        if duplicate_window.total_seconds() > 0:
            existing_near = db.execute(
                select(AttendanceEvent.id).where(
                    AttendanceEvent.device_id == device_id,
                    AttendanceEvent.employee_code == employee_code,
                    AttendanceEvent.punch_type == punch_type,
                    AttendanceEvent.timestamp >= r.timestamp - duplicate_window,
                    AttendanceEvent.timestamp <= r.timestamp + duplicate_window,
                ).limit(1)
            ).scalar_one_or_none()
            if existing_near is not None:
                continue
        mapping = resolve_mapping_for_punch(
            db,
            device_id=device_id,
            device_user_id=employee_code,
            at_time=r.timestamp,
        )
        stmt = (
            pg_insert(AttendanceEvent)
            .values(
                event_uuid=str(uuid4()),
                employee_code=employee_code,
                timestamp=r.timestamp,
                device_id=device_id,
                employee_uuid=mapping.employee_uuid if mapping else None,
                device_mapping_id=mapping.id if mapping else None,
                punch_type=punch_type,
                source=source,
                sync_batch_uuid=sync_batch_uuid,
            )
            .on_conflict_do_nothing(constraint="uq_event_device_employee_ts")
        )
        res = db.execute(stmt)
        if res.rowcount is not None and res.rowcount > 0:
            rows += res.rowcount
    db.commit()
    return rows


def append_device_day_events(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    device_records: Sequence[DeviceAttendanceRecord],
    device_id: str,
    source: str = "device_verification",
) -> list[datetime]:
    """Append device punches for one employee-day without deleting anything."""
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    start_utc, end_utc = _day_bounds_utc(local_date, settings.timezone)
    employee_code = str(employee.device_user_id)
    day_records = [
        r
        for r in device_records
        if r.user_id == employee_code and start_utc <= r.timestamp.astimezone(ZoneInfo("UTC")) < end_utc
    ]
    append_attendance_events_idempotent(db, day_records, device_id, source=source)
    return [r.timestamp for r in day_records]


def effective_punches_for_summary(
    db: Session,
    *,
    summary_date: date,
    settings: Settings | None = None,
) -> dict[int, list[AttendanceEffectivePunch]]:
    """Load active effective punches grouped by employee_id for a local date."""
    settings = settings or get_settings()
    rows = list(
        db.execute(
            select(AttendanceEffectivePunch).where(
                AttendanceEffectivePunch.local_date == summary_date,
                AttendanceEffectivePunch.is_active.is_(True),
            )
        ).scalars().all()
    )
    grouped: dict[int, list[AttendanceEffectivePunch]] = defaultdict(list)
    for row in rows:
        grouped[row.employee_id].append(row)
    for emp_id in grouped:
        grouped[emp_id].sort(key=lambda p: p.timestamp)
    return grouped


def load_day_snapshot_effective(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings | None = None,
) -> DayAttendanceSnapshot:
    """Build day snapshot from effective punches (read-only)."""
    cfg = settings or get_settings()
    punches = load_active_effective_punches(db, employee_id=employee.id, local_date=local_date)
    if not punches:
        first_in, last_out, total_min, _ = summarize_employee_day_from_events(
            db, employee=employee, local_date=local_date, settings=cfg
        )
        return DayAttendanceSnapshot(
            local_date=local_date,
            first_check_in=first_in,
            last_check_out=last_out,
            log_ids=[],
            log_timestamps=[first_in, last_out] if first_in or last_out else [],
        )

    first_in, last_out, _ = summarize_day_punches(punches, tz_name=cfg.timezone)
    return DayAttendanceSnapshot(
        local_date=local_date,
        first_check_in=first_in,
        last_check_out=last_out,
        log_ids=[p.id for p in punches],
        log_timestamps=[p.timestamp for p in punches],
    )


def verify_imported_timestamps(
    *,
    expected_in: datetime | None,
    expected_out: datetime | None,
    imported_timestamps: list[datetime],
    tz_name: str,
) -> tuple[bool, bool]:
    has_in = expected_in is not None and any(
        _ts_match(ts, expected_in, tz_name=tz_name) for ts in imported_timestamps
    )
    has_out = True
    if expected_out is not None:
        has_out = any(_ts_match(ts, expected_out, tz_name=tz_name) for ts in imported_timestamps)
    return has_in, has_out
