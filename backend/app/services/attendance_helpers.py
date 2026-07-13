"""Shared attendance utilities (suppression, local dates, pairing, device mapping)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.attendance_log import AttendanceLog
from app.models.attendance_sync_suppression import AttendanceSyncSuppression
from app.models.device_user_mapping import DeviceUserMapping
from app.services.device_attlog_protocol import _ts_match
from app.services.punch_classification import classify_punch


def is_suppressed_timestamp(
    db: Session,
    *,
    device_id: str,
    employee_code: str,
    timestamp: datetime,
    settings: Settings | None = None,
) -> bool:
    """Match suppressions with ±2s tolerance (aligned with device attlog verify)."""
    cfg = settings or get_settings()
    tz_name = cfg.timezone
    window = timedelta(seconds=2)
    if timestamp.tzinfo is None:
        ts_aware = timestamp.replace(tzinfo=ZoneInfo("UTC"))
    else:
        ts_aware = timestamp
    rows = db.execute(
        select(AttendanceSyncSuppression.suppressed_timestamp).where(
            AttendanceSyncSuppression.device_id == device_id,
            AttendanceSyncSuppression.employee_code == employee_code,
            AttendanceSyncSuppression.suppressed_timestamp >= ts_aware - window,
            AttendanceSyncSuppression.suppressed_timestamp <= ts_aware + window,
        )
    ).all()
    for (sup_ts,) in rows:
        if _ts_match(timestamp, sup_ts, tz_name=tz_name):
            return True
    return False


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def resolve_mapping_for_punch(
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


def pair_logs_for_day(
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
