#!/usr/bin/env python3
"""
Read-only copy from the ZKTeco terminal into PostgreSQL:
  1) Users → employees table (upsert / refresh device fields)
  2) Attendance → attendance_logs + session pairing for today/yesterday

Requires a registered device (Settings UI) or bootstrap ZK_DEVICE_* defaults.
Run from repo:
  cd backend && .venv/bin/python scripts/sync_from_device.py
  cd backend && .venv/bin/python scripts/sync_from_device.py --incremental
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.domains.attendance.services.attendance_service import run_device_sync, run_user_sync  # noqa: E402
from app.domains.devices.services.device_registry_service import ensure_default_device  # noqa: E402
from app.core.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync users and attendance from the ZK terminal")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Use incremental sync floor (default is full history pull of everything still on the device)",
    )
    args = parser.parse_args()
    full = not args.incremental

    settings = get_settings()
    db = SessionLocal()
    try:
        ensure_default_device(db, settings=settings)
        db.commit()

        print("Step 1/2: Fetching users from device (get_users)…")
        u_total, u_inserted = run_user_sync(db, settings=settings)
        print(f"  Users on device: {u_total}; new rows inserted into DB: {u_inserted}")

        mode = "FULL (all attendance still on device)" if full else "incremental"
        print(f"Step 2/2: Fetching attendance from device ({mode})…")
        a_fetched, a_inserted, placeholders = run_device_sync(
            db, full_resync=full, settings=settings
        )
        print(f"  Attendance rows from device: {a_fetched}; new log rows inserted: {a_inserted}")
        print(f"  Placeholder employees from orphan punch codes: {placeholders}")
        print("Done. Sessions rebuilt for SESSION_REBUILD_LOOKBACK_DAYS (local timezone).")
        if full:
            print(
                "Full sync complete. Only punches still stored on the terminal can be imported; "
                "older evenings already rolled off the device must be fixed via Attendance Adjust."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
