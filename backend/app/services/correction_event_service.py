"""Idempotent correction event ledger for internal forensic access."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.attendance_correction_event import AttendanceCorrectionEvent


def record_correction_event(
    db: Session,
    *,
    correction_uuid: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    device_operation_uuid: str | None = None,
) -> AttendanceCorrectionEvent | None:
    """
    Append a correction workflow event. Returns None if device_operation_uuid already recorded
    (idempotent guard against duplicate finalize/recovery).
    """
    event_uuid = str(uuid4())
    op_uuid = device_operation_uuid or event_uuid
    stmt = (
        pg_insert(AttendanceCorrectionEvent)
        .values(
            event_uuid=event_uuid,
            correction_uuid=correction_uuid,
            device_operation_uuid=op_uuid,
            event_type=event_type,
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_correction_device_operation_uuid")
        .returning(AttendanceCorrectionEvent.id)
    )
    row_id = db.execute(stmt).scalar_one_or_none()
    if row_id is None:
        return None
    return db.get(AttendanceCorrectionEvent, row_id)


def correction_event_exists(
    db: Session,
    *,
    correction_uuid: str,
    event_type: str,
) -> bool:
    from sqlalchemy import select

    return (
        db.execute(
            select(AttendanceCorrectionEvent.id).where(
                AttendanceCorrectionEvent.correction_uuid == correction_uuid,
                AttendanceCorrectionEvent.event_type == event_type,
            ).limit(1)
        ).scalar_one_or_none()
        is not None
    )
