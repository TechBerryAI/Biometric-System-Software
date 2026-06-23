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
from app.models.attendance_effective_punch import AttendanceEffectivePunch
from app.models.attendance_event import AttendanceEvent
from app.models.attendance_session import AttendanceSession
from app.models.attendance_sync_suppression import AttendanceSyncSuppression
from app.models.employee import Employee
from app.services.attendance_helpers import (
    is_suppressed_timestamp,
    pair_logs_for_day,
    resolve_mapping_for_punch,
)
from app.services.device_attlog_protocol import _ts_match
from app.services.device_service import DeviceAttendanceRecord
from app.services.punch_classification import classify_punch

logger = logging.getLogger(__name__)

PUNCH_IN = "0"
PUNCH_OUT = "1"


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


def _dedupe_events_for_effective(
    events: Sequence[AttendanceEvent],
    *,
    settings: Settings,
) -> list[AttendanceEvent]:
    """Collapse near-duplicate events without deleting stored events."""
    window = timedelta(seconds=settings.duplicate_punch_window_seconds)
    if window.total_seconds() <= 0:
        return list(events)
    out: list[AttendanceEvent] = []
    last_seen: dict[tuple[str, str], datetime] = {}
    for row in sorted(events, key=lambda e: e.timestamp):
        key = (row.punch_type, row.employee_code)
        prev = last_seen.get(key)
        if prev is not None and row.timestamp - prev <= window:
            continue
        out.append(row)
        last_seen[key] = row.timestamp
    return out


def _events_for_employee_day(
    db: Session,
    *,
    employee: Employee,
    local_date: date,
    settings: Settings,
) -> list[AttendanceEvent]:
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
    rows = list(db.execute(q.order_by(AttendanceEvent.timestamp)).scalars().all())
    filtered: list[AttendanceEvent] = []
    for ev in rows:
        if is_suppressed_timestamp(
            db,
            device_id=ev.device_id,
            employee_code=ev.employee_code,
            timestamp=ev.timestamp,
            settings=settings,
        ):
            continue
        filtered.append(ev)
    return _dedupe_events_for_effective(filtered, settings=settings)


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
    events = _events_for_employee_day(db, employee=employee, local_date=local_date, settings=settings)

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
    for ev in events:
        db.add(
            AttendanceEffectivePunch(
                employee_id=employee.id,
                local_date=local_date,
                punch_type=ev.punch_type,
                timestamp=ev.timestamp,
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
        punch_type = str(r.punch)
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
    """Build day snapshot from effective punches (what all screens display)."""
    cfg = settings or get_settings()
    punches = load_active_effective_punches(db, employee_id=employee.id, local_date=local_date)
    if not punches:
        sync_effective_punches_from_events(db, employee=employee, local_date=local_date, settings=cfg, commit=True)
        punches = load_active_effective_punches(db, employee_id=employee.id, local_date=local_date)

    ins = [p.timestamp for p in punches if classify_punch(p.punch_type) is True]
    outs = [p.timestamp for p in punches if classify_punch(p.punch_type) is False]
    first_in = min(ins) if ins else (punches[0].timestamp if punches else None)
    last_out = max(outs) if outs else (punches[-1].timestamp if len(punches) > 1 else None)
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
