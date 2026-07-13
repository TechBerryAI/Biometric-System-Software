#!/usr/bin/env python3
"""Reprocess stuck CORRECT_ATTENDANCE commands and recover orphan corrections."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.attendance_correction import AttendanceCorrection
from app.models.device_command import DeviceCommand, DeviceCommandStatus
from app.services.attendance_correction_service import (
    CORRECTION_STATUS_DEVICE_PENDING,
    CORRECTION_STATUS_PENDING,
    mark_correction_failed_for_command,
    recover_orphan_correction,
)
from app.services.device_command_service import _utcnow, reprocess_device_command


def main() -> int:
    settings = get_settings()
    stale_cutoff = _utcnow() - timedelta(minutes=settings.command_stale_minutes)
    db = SessionLocal()
    actions = 0
    try:
        orphans = list(
            db.execute(
                select(AttendanceCorrection).where(
                    AttendanceCorrection.status.in_(
                        (CORRECTION_STATUS_PENDING, CORRECTION_STATUS_DEVICE_PENDING)
                    ),
                    AttendanceCorrection.device_command_uuid.is_(None),
                )
            ).scalars().all()
        )
        for correction in orphans:
            print(
                f"Recovering orphan correction {correction.correction_uuid} "
                f"(status={correction.status}, employee={correction.employee_id})"
            )
            try:
                updated = recover_orphan_correction(db, correction)
                db.commit()
                db.refresh(updated)
                print(f"  -> status={updated.status}, error={updated.error_message}")
                actions += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"  -> failed: {exc}")

        stale_commands = list(
            db.execute(
                select(DeviceCommand)
                .where(
                    DeviceCommand.command_type == "CORRECT_ATTENDANCE",
                    DeviceCommand.status == DeviceCommandStatus.RETRYING.value,
                    DeviceCommand.created_at <= stale_cutoff,
                )
                .order_by(DeviceCommand.created_at.asc())
            ).scalars().all()
        )
        for command in stale_commands:
            print(
                f"Force-failing stale command {command.command_uuid} "
                f"(retries={command.retries}, last_error={command.last_error})"
            )
            command.status = DeviceCommandStatus.FAILED.value
            command.completed_at = _utcnow()
            command.last_error = (command.last_error or "Stale RETRYING command force-terminated.")[:2000]
            mark_correction_failed_for_command(
                db,
                command_uuid=command.command_uuid,
                error_message=command.last_error,
            )
            db.commit()
            print(f"  -> status={command.status}")
            actions += 1

        commands = list(
            db.execute(
                select(DeviceCommand)
                .where(
                    DeviceCommand.command_type == "CORRECT_ATTENDANCE",
                    DeviceCommand.status.in_(
                        [
                            DeviceCommandStatus.PENDING.value,
                            DeviceCommandStatus.RETRYING.value,
                            DeviceCommandStatus.FAILED.value,
                        ]
                    ),
                )
                .order_by(DeviceCommand.created_at.asc())
            ).scalars().all()
        )
        for command in commands:
            print(f"Reprocessing {command.command_uuid} (status={command.status}, retries={command.retries})")
            try:
                updated = reprocess_device_command(db, command.command_uuid, worker_id="script-reprocess")
                db.refresh(updated)
                print(f"  -> status={updated.status}, error={updated.last_error}")
                actions += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                print(f"  -> failed: {exc}")

        if actions == 0:
            print("No stuck corrections or commands found.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
