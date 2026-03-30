#!/usr/bin/env python3
"""One-shot attendance poll (same logic as Celery task; useful for debugging)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running from repo: python scripts/poll_device.py
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.services.attendance_service import run_device_sync  # noqa: E402

logging.basicConfig(level=logging.INFO)


def main() -> None:
    db = SessionLocal()
    try:
        fetched, inserted = run_device_sync(db)
        print(f"Fetched {fetched} records from device, inserted {inserted} new log rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
