#!/usr/bin/env python3
"""One-shot user sync from device (ON CONFLICT DO NOTHING on device_user_id)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.services.attendance_service import run_user_sync  # noqa: E402

logging.basicConfig(level=logging.INFO)


def main() -> None:
    db = SessionLocal()
    try:
        total, inserted = run_user_sync(db)
        print(f"Device returned {total} users; {inserted} new rows inserted (rest already existed).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
