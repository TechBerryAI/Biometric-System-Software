#!/usr/bin/env python3
"""Restore biometric device to NORMAL mode so DELETE_USER / UPSERT_USER can run."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.services.employee_offboard_service import restore_device_writable_state  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        previous = restore_device_writable_state(db)
        db.commit()
        print(f"Device mode: {previous} -> NORMAL (runtime risk reset to LOW)")
        print("You can now retry device cleanup:")
        print("  python scripts/purge_departed_employees.py --device-only --execute")
    finally:
        db.close()


if __name__ == "__main__":
    main()
