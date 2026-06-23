#!/usr/bin/env python3
"""
Append-only resync from biometric device (never deletes attendance history).

Use to backfill missing punches after connectivity gaps. Historical records are preserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.services.attendance_service import run_device_sync, run_user_sync  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        print("Syncing users from device (append-only) ...")
        users_total, users_inserted = run_user_sync(db)
        print(f"  Users on device: {users_total}; upserted: {users_inserted}")

        print("Syncing attendance from device (append-only) ...")
        logs_fetched, logs_inserted, placeholders = run_device_sync(db, full_resync=True)
        print(f"  Attendance fetched: {logs_fetched}; new rows: {logs_inserted}; placeholders: {placeholders}")
        print("Done. No attendance history was deleted.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
