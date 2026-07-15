#!/usr/bin/env python3
"""
Import Softworks / eTimeTrack monthly Four-Punch XLS into attendance_logs.

Safety guarantees:
  - Never DELETE or UPDATE existing attendance_logs rows
  - INSERT only via the same idempotent path as device sync (unique + near-dup skip)
  - Softworks punches within DUPLICATE_PUNCH_WINDOW of *any* existing punch for that
    employee are skipped (avoids twin rows when Softworks has HH:MM and device has HH:MM:SS)
  - March+ files in the Jul 2026 dump are typically all-Absent with zero time cells —
    they contribute nothing; DB data from March onward is left intact

Usage (from repo):
  cd backend && .venv/bin/python scripts/import_softworks_attendance.py
  cd backend && .venv/bin/python scripts/import_softworks_attendance.py --dry-run
  cd backend && .venv/bin/python scripts/import_softworks_attendance.py --dir ../imports/Attendance
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.domains.attendance.models.attendance_log import AttendanceLog  # noqa: E402
from app.domains.employees.models.employee import Employee  # noqa: E402
from app.domains.attendance.services.attendance_helpers import (  # noqa: E402
    rebuild_sessions_for_employee_date,
)
from app.domains.attendance.services.attendance_service import (  # noqa: E402
    backfill_employees_from_orphan_logs,
    insert_attendance_logs_idempotent,
)
from app.domains.attendance.services.softworks_xls_parser import (  # noqa: E402
    SoftworksPunch,
    iter_softworks_month_files,
    parse_four_punch_workbook,
)
from app.domains.devices.services.device_service import DeviceAttendanceRecord  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("import_softworks")

_DEFAULT_DIRS = (
    Path(__file__).resolve().parents[2] / "imports" / "Attendance",
    Path(__file__).resolve().parents[2] / "Attendance" / "Attendance",
)


def _resolve_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_dir():
            raise SystemExit(f"Directory not found: {explicit}")
        return explicit
    for candidate in _DEFAULT_DIRS:
        if candidate.is_dir() and any(candidate.glob("*.xls")):
            return candidate
    raise SystemExit(
        "No Softworks Attendance folder found. Pass --dir pointing at the monthly .xls exports."
    )


def _to_device_records(punches: list[SoftworksPunch]) -> list[DeviceAttendanceRecord]:
    records: list[DeviceAttendanceRecord] = []
    for punch in punches:
        # status encodes check direction for device_attendance_punch_type
        status = 0 if punch.direction == "in" else 1
        records.append(
            DeviceAttendanceRecord(
                user_id=punch.employee_code,
                timestamp=punch.timestamp,
                punch=0,
                status=status,
            )
        )
    # Stable order helps near-dup checks
    records.sort(key=lambda r: (r.user_id, r.timestamp, r.status))
    return records


def _filter_already_present(
    db,
    records: list[DeviceAttendanceRecord],
    *,
    window: timedelta,
) -> tuple[list[DeviceAttendanceRecord], int]:
    """Drop Softworks punches that already have any log for that employee within window."""
    if not records:
        return [], 0
    kept: list[DeviceAttendanceRecord] = []
    skipped = 0
    for record in records:
        exists = db.execute(
            select(AttendanceLog.id)
            .where(
                AttendanceLog.employee_code == record.user_id,
                AttendanceLog.timestamp >= record.timestamp - window,
                AttendanceLog.timestamp <= record.timestamp + window,
            )
            .limit(1)
        ).scalar_one_or_none()
        if exists is not None:
            skipped += 1
            continue
        kept.append(record)
    return kept, skipped


def _rebuild_sessions_for_days(
    db,
    *,
    employee_days: set[tuple[str, date]],
    settings,
) -> int:
    if not employee_days:
        return 0
    codes = {code for code, _ in employee_days}
    employees = {
        str(e.device_user_id): e
        for e in db.execute(select(Employee).where(Employee.device_user_id.in_(codes))).scalars().all()
    }
    rebuilt = 0
    for code, day in sorted(employee_days):
        emp = employees.get(code)
        if emp is None:
            continue
        rebuild_sessions_for_employee_date(
            db, employee_id=emp.id, local_date=day, settings=settings, commit=False
        )
        rebuilt += 1
    if rebuilt:
        db.commit()
    return rebuilt


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Softworks four-punch monthly XLS into attendance_logs")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Folder containing Softworks monthly .xls files (default: imports/Attendance)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report only; do not write to the database",
    )
    parser.add_argument(
        "--through-month",
        type=str,
        default="2026-02",
        help="Import months up to and including YYYY-MM (default 2026-02: Softworks had data through Feb)",
    )
    parser.add_argument(
        "--no-session-rebuild",
        action="store_true",
        help="Skip rebuilding attendance sessions after insert",
    )
    parser.add_argument(
        "--rebuild-sessions-only",
        action="store_true",
        help="Do not insert; only rebuild sessions for Softworks punch employee-days",
    )
    args = parser.parse_args()

    through_year, through_month = (int(x) for x in args.through_month.split("-", 1))
    through_key = (through_year, through_month)

    directory = _resolve_dir(args.dir)
    settings = get_settings()
    files = iter_softworks_month_files(directory)
    if not files:
        raise SystemExit(f"No Softworks monthly .xls files found in {directory}")

    all_punches: list[SoftworksPunch] = []
    print(f"Source directory: {directory}")
    for path, year, month in files:
        punches = parse_four_punch_workbook(
            path, year=year, month=month, timezone=settings.timezone
        )
        marker = ""
        if (year, month) > through_key:
            marker = " (beyond --through-month; skipped)"
        elif not punches:
            marker = " (no punch cells — Softworks empty for this month)"
        print(f"  {path.name}: {len(punches)} punches{marker}")
        if (year, month) <= through_key and punches:
            all_punches.extend(punches)

    print(f"Softworks punches selected: {len(all_punches)}")
    if not all_punches:
        print("Nothing to import.")
        return

    tz = ZoneInfo(settings.timezone)
    employee_days = {(p.employee_code, p.timestamp.astimezone(tz).date()) for p in all_punches}

    if args.rebuild_sessions_only:
        if args.dry_run:
            print(f"Dry run — would rebuild {len(employee_days)} employee-days")
            return
        db = SessionLocal()
        try:
            rebuilt = _rebuild_sessions_for_days(
                db, employee_days=employee_days, settings=settings
            )
            print(f"Sessions rebuilt for {rebuilt} employee-days (from Softworks punch days)")
        finally:
            db.close()
        return

    records = _to_device_records(all_punches)
    db = SessionLocal()
    try:
        before = db.execute(select(func.count()).select_from(AttendanceLog)).scalar_one()
        window = timedelta(seconds=settings.duplicate_punch_window_seconds)
        filtered, skipped_existing = _filter_already_present(db, records, window=window)
        print(
            f"DB attendance_logs before: {before}; "
            f"already-present skips: {skipped_existing}; "
            f"candidates to insert: {len(filtered)}"
        )

        if args.dry_run:
            print("Dry run — no changes written.")
            return

        inserted = insert_attendance_logs_idempotent(db, filtered, settings.zk_device_id)
        placeholders = backfill_employees_from_orphan_logs(db)
        after = db.execute(select(func.count()).select_from(AttendanceLog)).scalar_one()
        # SQLAlchemy/psycopg may report ON CONFLICT rowcount as -1; trust table delta.
        delta = after - before
        effective_inserted = delta if delta > 0 else max(inserted, 0)

        print(f"Insert API count: {inserted}; placeholder employees: {placeholders}")
        print(f"DB attendance_logs after: {after} (delta={delta})")
        if after < before:
            raise SystemExit("ERROR: log count decreased — aborting session rebuild")

        if not args.no_session_rebuild and (effective_inserted > 0 or filtered):
            rebuild_days = {
                (r.user_id, r.timestamp.astimezone(tz).date()) for r in filtered
            }
            rebuilt = _rebuild_sessions_for_days(
                db, employee_days=rebuild_days, settings=settings
            )
            print(f"Sessions rebuilt for {rebuilt} employee-days")
        print("Done. Existing punches were preserved; Softworks only filled gaps.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
