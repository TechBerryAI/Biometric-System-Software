#!/usr/bin/env python3
"""Recovery utilities for attendance sync gaps and duplicate punches."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services.attendance_service import (  # noqa: E402
    prune_recent_duplicate_logs,
    rebuild_sessions_for_local_date,
    run_device_sync,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile attendance logs and sessions.")
    parser.add_argument("--full-sync", action="store_true", help="Pull all device attendance (ignore incremental floor)")
    parser.add_argument("--rebuild-days", type=int, default=0, help="Rebuild sessions for trailing local days")
    parser.add_argument("--prune-duplicates", action="store_true", help="Prune near-duplicate punches in lookback horizon")
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    try:
        if args.full_sync:
            fetched, inserted, placeholders = run_device_sync(db, full_resync=True)
            print(f"Full sync: fetched={fetched} inserted={inserted} placeholders={placeholders}")
        if args.prune_duplicates:
            deleted = prune_recent_duplicate_logs(db, settings=settings)
            print(f"Pruned duplicate logs: {deleted}")
        if args.rebuild_days > 0:
            tz = ZoneInfo(settings.timezone)
            today = datetime.now(tz).date()
            for offset in range(args.rebuild_days):
                day = today - timedelta(days=offset)
                created = rebuild_sessions_for_local_date(db, day, settings=settings)
                print(f"Rebuilt sessions for {day.isoformat()}: {created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
