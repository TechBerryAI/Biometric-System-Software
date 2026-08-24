#!/usr/bin/env python3
"""Repair 12-hour AM/PM biometric clock shift and optionally sync the terminal to IST.

Default is dry-run. Production apply:

  cd backend && .venv/bin/python scripts/repair_twelve_hour_clock_shift.py --apply --sync-clock
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.domains.attendance.services.attendance_service import _persist_clock_drift  # noqa: E402
from app.domains.attendance.services.clock_shift_repair import repair_twelve_hour_clock_shift  # noqa: E402
from app.domains.devices.services.device_command_service import device_session_lock  # noqa: E402
from app.domains.devices.services.device_registry_service import device_service_for, ensure_default_device  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_clock_shift")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write skip keys, +12h timestamps, rebuild sessions")
    parser.add_argument("--sync-clock", action="store_true", help="Write IST wall clock to the terminal")
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    try:
        device = ensure_default_device(db, settings)
        db.commit()

        report = repair_twelve_hour_clock_shift(db, apply=args.apply, settings=settings)
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"{mode}: matched={report.matched} updated={report.updated} deleted_dupes={report.deleted_duplicates} skip_rows={report.skip_rows}")
        print(f"  sessions_rebuilt={report.sessions_rebuilt} employee_days={len(report.employee_days)}")
        if report.employee_days[:12]:
            print("  sample days:", ", ".join(report.employee_days[:12]))

        if args.sync_clock:
            with device_session_lock(device.name, settings, blocking_timeout=max(settings.zk_device_timeout_seconds, 60)):
                service = device_service_for(db, device_name=device.name, settings=settings)
                synced_at = service.sync_device_time()
            drift = service.last_clock_drift_seconds
            _persist_clock_drift(db, device.name, drift)
            db.commit()
            print(f"SYNC_TIME: wrote IST wall {synced_at.isoformat()} drift_after={drift}")
            if drift is not None and abs(drift) > 120:
                print("WARNING: device clock still more than 2 minutes off IST after sync.")
                sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
