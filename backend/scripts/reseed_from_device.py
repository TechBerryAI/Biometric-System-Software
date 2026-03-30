#!/usr/bin/env python3
"""
Reset copied attendance tables and pull a fresh copy from biometric device.

Use when timezone/device-identity parsing changed and old copied rows are inconsistent.
Device remains read-only (get_users/get_attendance only).
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import delete

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.models.attendance_log import AttendanceLog  # noqa: E402
from app.models.attendance_session import AttendanceSession  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.services.attendance_service import run_device_sync, run_user_sync  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        print("Clearing copied tables: attendance_sessions, attendance_logs, employees ...")
        db.execute(delete(AttendanceSession))
        db.execute(delete(AttendanceLog))
        db.execute(delete(Employee))
        db.commit()

        print("Syncing users from device ...")
        users_total, users_inserted = run_user_sync(db)
        print(f"  Users on device: {users_total}; inserted: {users_inserted}")

        print("Syncing attendance from device ...")
        logs_fetched, logs_inserted = run_device_sync(db)
        print(f"  Attendance fetched: {logs_fetched}; inserted: {logs_inserted}")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

