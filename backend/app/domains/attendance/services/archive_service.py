"""Archive old attendance partitions / cold data beyond retention."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domains.attendance.models.archive_run import AttendanceArchiveRun
from app.domains.attendance.models.attendance_log import AttendanceLog

logger = logging.getLogger(__name__)


def archive_old_attendance(
    db: Session,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Archive attendance logs older than retention_days.

    On PostgreSQL with native partitions, operators should DETACH partitions and
    set storage_uri on the run record. This job:
      1) Counts eligible rows
      2) Records an attendance_archive_runs row
      3) Optionally deletes cold rows when ATTENDANCE_ARCHIVE_DELETE=true
         (default false — prefer detach/export over DELETE for large tables)
    """
    settings = settings or get_settings()
    retention_days = settings.attendance_archive_retention_days
    tz = ZoneInfo("UTC")
    cutoff = datetime.now(tz) - timedelta(days=retention_days)
    period_start = db.execute(
        select(func.min(AttendanceLog.timestamp)).where(AttendanceLog.timestamp < cutoff)
    ).scalar_one_or_none()
    if period_start is None:
        return {"archived": 0, "skipped": True, "reason": "no_eligible_rows"}

    row_count = db.execute(
        select(func.count()).select_from(AttendanceLog).where(AttendanceLog.timestamp < cutoff)
    ).scalar_one()

    run = AttendanceArchiveRun(
        run_uuid=str(uuid4()),
        partition_name=None,
        period_start=period_start,
        period_end=cutoff,
        row_count=int(row_count or 0),
        status="dry_run" if dry_run else "running",
        metadata_json={"retention_days": retention_days, "cutoff": cutoff.isoformat()},
    )
    db.add(run)
    db.flush()

    if dry_run or not settings.attendance_archive_delete:
        run.status = "recorded"
        run.detail = (
            "Metadata recorded; set ATTENDANCE_ARCHIVE_DELETE=true to delete, "
            "or DETACH the corresponding PostgreSQL partition and set storage_uri."
        )
        run.completed_at = datetime.now(tz)
        db.flush()
        logger.info(
            "Archive run %s recorded %s rows before %s (delete=%s)",
            run.run_uuid,
            run.row_count,
            cutoff.isoformat(),
            settings.attendance_archive_delete,
        )
        return {
            "run_uuid": run.run_uuid,
            "archived": 0,
            "eligible": run.row_count,
            "status": run.status,
        }

    deleted = db.execute(
        delete(AttendanceLog).where(AttendanceLog.timestamp < cutoff)
    )
    run.row_count = int(deleted.rowcount or 0)
    run.status = "completed"
    run.completed_at = datetime.now(tz)
    run.detail = f"Deleted {run.row_count} cold attendance_logs rows"
    db.flush()
    logger.info("Archive run %s deleted %s rows", run.run_uuid, run.row_count)
    return {
        "run_uuid": run.run_uuid,
        "archived": run.row_count,
        "eligible": run.row_count,
        "status": run.status,
    }
