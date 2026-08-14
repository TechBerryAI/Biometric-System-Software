"""Detect employee-days that lack a real second punch (missing check-out)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings


def count_incomplete_attendance_days(
    db: Session,
    *,
    lookback_days: int = 30,
    min_span_minutes: int | None = None,
    settings: Settings | None = None,
    include_today: bool = False,
) -> int:
    """
    Count weekday employee-days in the lookback window with fewer than two punches
    spanning at least ``min_span_minutes`` (default from settings, usually 5).

    Excludes today by default so in-progress shifts are not flagged as missing OUT.
    """
    settings = settings or get_settings()
    span_minutes = (
        settings.open_day_min_span_minutes if min_span_minutes is None else max(int(min_span_minutes), 1)
    )
    tz_name = settings.resolved_timezone()
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    end_day = now_local.date() if include_today else now_local.date() - timedelta(days=1)
    start_day = end_day - timedelta(days=max(lookback_days, 1) - 1)
    if end_day < start_day:
        return 0

    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        row = db.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                  SELECT
                    employee_code,
                    date(timestamp) AS d,
                    MIN(timestamp) AS first_ts,
                    MAX(timestamp) AS last_ts,
                    COUNT(*) AS punch_count
                  FROM attendance_logs
                  WHERE date(timestamp) >= :start_day
                    AND date(timestamp) <= :end_day
                  GROUP BY employee_code, date(timestamp)
                ) day_span
                WHERE CAST(strftime('%w', d) AS INTEGER) BETWEEN 1 AND 5
                  AND (
                    punch_count < 2
                    OR (strftime('%s', last_ts) - strftime('%s', first_ts)) < :span_seconds
                  )
                """
            ),
            {
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
                "span_seconds": span_minutes * 60,
            },
        ).scalar()
        return int(row or 0)

    row = db.execute(
        text(
            """
            WITH day_span AS (
              SELECT
                employee_code,
                (timestamp AT TIME ZONE :tz)::date AS d,
                MIN(timestamp AT TIME ZONE :tz) AS first_ts,
                MAX(timestamp AT TIME ZONE :tz) AS last_ts,
                COUNT(*) AS punch_count
              FROM attendance_logs
              WHERE (timestamp AT TIME ZONE :tz)::date >= CAST(:start_day AS date)
                AND (timestamp AT TIME ZONE :tz)::date <= CAST(:end_day AS date)
              GROUP BY employee_code, (timestamp AT TIME ZONE :tz)::date
            )
            SELECT COUNT(*)
            FROM day_span
            WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
              AND (
                punch_count < 2
                OR EXTRACT(EPOCH FROM (last_ts - first_ts)) < :span_seconds
              )
            """
        ),
        {
            "tz": tz_name,
            "start_day": start_day.isoformat(),
            "end_day": end_day.isoformat(),
            "span_seconds": span_minutes * 60,
        },
    ).scalar()
    return int(row or 0)


def list_incomplete_attendance_days(
    db: Session,
    *,
    lookback_days: int = 14,
    limit: int = 25,
    min_span_minutes: int | None = None,
    settings: Settings | None = None,
    include_today: bool = False,
) -> list[dict[str, object]]:
    """Sample incomplete employee-days for ops dashboards."""
    settings = settings or get_settings()
    span_minutes = (
        settings.open_day_min_span_minutes if min_span_minutes is None else max(int(min_span_minutes), 1)
    )
    tz_name = settings.resolved_timezone()
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    end_day = now_local.date() if include_today else now_local.date() - timedelta(days=1)
    start_day = end_day - timedelta(days=max(lookback_days, 1) - 1)
    if end_day < start_day:
        return []

    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        rows = db.execute(
            text(
                """
                SELECT employee_code, d, punch_count, first_ts, last_ts FROM (
                  SELECT
                    employee_code,
                    date(timestamp) AS d,
                    MIN(timestamp) AS first_ts,
                    MAX(timestamp) AS last_ts,
                    COUNT(*) AS punch_count
                  FROM attendance_logs
                  WHERE date(timestamp) >= :start_day
                    AND date(timestamp) <= :end_day
                  GROUP BY employee_code, date(timestamp)
                ) day_span
                WHERE CAST(strftime('%w', d) AS INTEGER) BETWEEN 1 AND 5
                  AND (
                    punch_count < 2
                    OR (strftime('%s', last_ts) - strftime('%s', first_ts)) < :span_seconds
                  )
                ORDER BY d DESC, employee_code
                LIMIT :limit
                """
            ),
            {
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
                "span_seconds": span_minutes * 60,
                "limit": limit,
            },
        ).mappings().all()
    else:
        rows = db.execute(
            text(
                """
                WITH day_span AS (
                  SELECT
                    employee_code,
                    (timestamp AT TIME ZONE :tz)::date AS d,
                    MIN(timestamp AT TIME ZONE :tz) AS first_ts,
                    MAX(timestamp AT TIME ZONE :tz) AS last_ts,
                    COUNT(*) AS punch_count
                  FROM attendance_logs
                  WHERE (timestamp AT TIME ZONE :tz)::date >= CAST(:start_day AS date)
                    AND (timestamp AT TIME ZONE :tz)::date <= CAST(:end_day AS date)
                  GROUP BY employee_code, (timestamp AT TIME ZONE :tz)::date
                )
                SELECT employee_code, d, punch_count, first_ts, last_ts
                FROM day_span
                WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
                  AND (
                    punch_count < 2
                    OR EXTRACT(EPOCH FROM (last_ts - first_ts)) < :span_seconds
                  )
                ORDER BY d DESC, employee_code
                LIMIT :limit
                """
            ),
            {
                "tz": tz_name,
                "start_day": start_day.isoformat(),
                "end_day": end_day.isoformat(),
                "span_seconds": span_minutes * 60,
                "limit": limit,
            },
        ).mappings().all()

    out: list[dict[str, object]] = []
    for row in rows:
        day_val = row["d"]
        if isinstance(day_val, date):
            day_str = day_val.isoformat()
        else:
            day_str = str(day_val)
        out.append(
            {
                "employee_code": str(row["employee_code"]),
                "local_date": day_str,
                "punch_count": int(row["punch_count"] or 0),
                "first_punch": row["first_ts"].isoformat() if row["first_ts"] is not None else None,
                "last_punch": row["last_ts"].isoformat() if row["last_ts"] is not None else None,
            }
        )
    return out
