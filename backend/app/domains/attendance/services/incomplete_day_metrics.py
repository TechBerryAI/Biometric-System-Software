"""Count weekday employee-days whose last stored punch is before a local hour threshold."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings


def count_incomplete_attendance_days(
    db: Session,
    *,
    lookback_days: int = 30,
    last_punch_before_hour: int = 15,
    settings: Settings | None = None,
) -> int:
    """
    Weekday employee-days in the lookback window where MAX(local punch) is before
    ``last_punch_before_hour`` (default 15:00). These often lack an evening punch.
    """
    settings = settings or get_settings()
    tz_name = settings.timezone
    tz = ZoneInfo(tz_name)
    start = datetime.now(tz) - timedelta(days=max(lookback_days, 1))
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        row = db.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                  SELECT employee_code, date(timestamp) AS d, MAX(timestamp) AS last_ts
                  FROM attendance_logs
                  WHERE timestamp >= :start
                  GROUP BY employee_code, date(timestamp)
                ) day_span
                WHERE CAST(strftime('%w', d) AS INTEGER) BETWEEN 1 AND 5
                  AND CAST(strftime('%H', last_ts) AS INTEGER) < :hour
                """
            ),
            {"start": start, "hour": last_punch_before_hour},
        ).scalar()
        return int(row or 0)
    row = db.execute(
        text(
            """
            WITH day_span AS (
              SELECT
                employee_code,
                (timestamp AT TIME ZONE :tz)::date AS d,
                MAX(timestamp AT TIME ZONE :tz) AS last_ts
              FROM attendance_logs
              WHERE timestamp >= :start
              GROUP BY employee_code, (timestamp AT TIME ZONE :tz)::date
            )
            SELECT COUNT(*)
            FROM day_span
            WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
              AND EXTRACT(HOUR FROM last_ts) < :hour
            """
        ),
        {"tz": tz_name, "start": start, "hour": last_punch_before_hour},
    ).scalar()
    return int(row or 0)
