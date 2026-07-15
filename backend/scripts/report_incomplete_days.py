#!/usr/bin/env python3
"""Report weekday employee-days whose last punch is before 15:00 (likely missing evening)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.domains.attendance.services.incomplete_day_metrics import (  # noqa: E402
    count_incomplete_attendance_days,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="Lookback calendar days")
    parser.add_argument("--hour", type=int, default=15, help="Last-punch hour threshold (local)")
    parser.add_argument("--limit", type=int, default=40, help="Max sample rows to print")
    args = parser.parse_args()

    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    start = datetime.now(tz) - timedelta(days=max(args.days, 1))
    db = SessionLocal()
    try:
        total = count_incomplete_attendance_days(
            db,
            lookback_days=args.days,
            last_punch_before_hour=args.hour,
            settings=settings,
        )
        print(f"Incomplete weekday days (last punch before {args.hour}:00, {args.days}d): {total}")
        rows = db.execute(
            text(
                """
                WITH day_span AS (
                  SELECT
                    employee_code,
                    (timestamp AT TIME ZONE :tz)::date AS d,
                    MIN(timestamp AT TIME ZONE :tz) AS first_ts,
                    MAX(timestamp AT TIME ZONE :tz) AS last_ts,
                    COUNT(*) AS n
                  FROM attendance_logs
                  WHERE timestamp >= :start
                  GROUP BY employee_code, (timestamp AT TIME ZONE :tz)::date
                )
                SELECT employee_code, d, n, first_ts, last_ts
                FROM day_span
                WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
                  AND EXTRACT(HOUR FROM last_ts) < :hour
                ORDER BY d DESC, employee_code
                LIMIT :limit
                """
            ),
            {"tz": settings.timezone, "start": start, "hour": args.hour, "limit": args.limit},
        ).mappings().all()
        for row in rows:
            print(
                f"  {row['d']} {row['employee_code']} punches={row['n']} "
                f"first={row['first_ts']} last={row['last_ts']}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
