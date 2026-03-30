#!/usr/bin/env python3
"""
Read-only copy from the ZKTeco terminal into PostgreSQL:
  1) Users → employees table (ON CONFLICT DO NOTHING)
  2) Attendance → attendance_logs + session pairing for today/yesterday

Requires backend/.env ZK_DEVICE_IP, ZK_DEVICE_PORT, etc.
Run from repo:  cd backend && .venv\\Scripts\\python.exe scripts\\sync_from_device.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.services.attendance_service import run_device_sync, run_user_sync  # noqa: E402

logging.basicConfig(level=logging.INFO)


def main() -> None:
    db = SessionLocal()
    try:
        print("Step 1/2: Fetching users from device (get_users)…")
        u_total, u_inserted = run_user_sync(db)
        print(f"  Users on device: {u_total}; new rows inserted into DB: {u_inserted}")

        print("Step 2/2: Fetching attendance from device (get_attendance)…")
        a_fetched, a_inserted = run_device_sync(db)
        print(f"  Attendance rows from device: {a_fetched}; new log rows inserted: {a_inserted}")
        print("Done. Sessions are rebuilt for today and yesterday (local timezone).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
