"""Internal forensic APIs for raw attendance events and correction history."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_operator_account
from app.models.attendance_correction import AttendanceCorrection
from app.models.attendance_correction_event import AttendanceCorrectionEvent
from app.models.attendance_event import AttendanceEvent
from app.models.device_command import DeviceCommand
from app.models.device_state_snapshot import DeviceStateSnapshot
from app.models.employee import Employee
from app.models.user import User
from app.services.daily_summary_service import day_bounds_utc

router = APIRouter(
    prefix="/forensics",
    tags=["forensics"],
    dependencies=[Depends(require_operator_account)],
)


class AttendanceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_uuid: str
    employee_code: str
    timestamp: datetime
    device_id: str
    punch_type: str
    source: str
    created_at: datetime


class CorrectionLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correction_uuid: str
    employee_id: int
    local_date: date
    previous_check_in: datetime | None
    previous_check_out: datetime | None
    new_check_in: datetime | None
    new_check_out: datetime | None
    status: str
    correction_mode: str | None
    device_tier: str | None
    applied_at: datetime | None
    created_at: datetime


class CorrectionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_uuid: str
    correction_uuid: str
    event_type: str
    payload: dict | None
    created_at: datetime


class DeviceVerificationRead(BaseModel):
    command_uuid: str
    verification_status: str | None
    verification_details: dict | None
    completed_at: datetime | None


class DeviceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    snapshot_type: str
    snapshot_hash: str
    user_count: int
    firmware_version: str | None
    captured_at: datetime


class CorrectionTimelineRead(BaseModel):
    correction: CorrectionLedgerRead
    events: list[CorrectionEventRead]
    device_verification: DeviceVerificationRead | None


@router.get("/raw-events", response_model=list[AttendanceEventRead])
def list_raw_events(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    employee_id: int | None = None,
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator_account),
) -> list[AttendanceEvent]:
    settings = get_settings()
    q = select(AttendanceEvent).order_by(AttendanceEvent.timestamp.desc()).limit(limit)
    if date_from is not None:
        start, _ = day_bounds_utc(date_from, settings.timezone)
        q = q.where(AttendanceEvent.timestamp >= start)
    if date_to is not None:
        _, end = day_bounds_utc(date_to, settings.timezone)
        q = q.where(AttendanceEvent.timestamp < end)
    if employee_id is not None:
        emp = db.get(Employee, employee_id)
        if emp is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        q = q.where(AttendanceEvent.employee_code == str(emp.device_user_id))
    return list(db.execute(q).scalars().all())


@router.get("/correction-ledger", response_model=list[CorrectionLedgerRead])
def list_correction_ledger(
    employee_id: int | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator_account),
) -> list[AttendanceCorrection]:
    q = select(AttendanceCorrection).order_by(AttendanceCorrection.created_at.desc()).limit(limit)
    if employee_id is not None:
        q = q.where(AttendanceCorrection.employee_id == employee_id)
    if date_from is not None:
        q = q.where(AttendanceCorrection.local_date >= date_from)
    if date_to is not None:
        q = q.where(AttendanceCorrection.local_date <= date_to)
    return list(db.execute(q).scalars().all())


@router.get("/correction-timeline/{correction_uuid}", response_model=CorrectionTimelineRead)
def get_correction_timeline(
    correction_uuid: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator_account),
) -> CorrectionTimelineRead:
    correction = db.execute(
        select(AttendanceCorrection).where(AttendanceCorrection.correction_uuid == str(correction_uuid))
    ).scalar_one_or_none()
    if correction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correction not found")

    events = list(
        db.execute(
            select(AttendanceCorrectionEvent)
            .where(AttendanceCorrectionEvent.correction_uuid == str(correction_uuid))
            .order_by(AttendanceCorrectionEvent.created_at)
        ).scalars().all()
    )

    device_verification: DeviceVerificationRead | None = None
    if correction.device_command_uuid:
        command = db.execute(
            select(DeviceCommand).where(DeviceCommand.command_uuid == correction.device_command_uuid)
        ).scalar_one_or_none()
        if command is not None:
            device_verification = DeviceVerificationRead(
                command_uuid=command.command_uuid,
                verification_status=command.verification_status,
                verification_details=command.verification_details,
                completed_at=command.completed_at,
            )

    return CorrectionTimelineRead(
        correction=CorrectionLedgerRead.model_validate(correction),
        events=[CorrectionEventRead.model_validate(e) for e in events],
        device_verification=device_verification,
    )


@router.get("/device-verification", response_model=list[DeviceVerificationRead])
def list_device_verification_history(
    correction_uuid: UUID | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator_account),
) -> list[DeviceVerificationRead]:
    if correction_uuid is not None:
        correction = db.execute(
            select(AttendanceCorrection).where(AttendanceCorrection.correction_uuid == str(correction_uuid))
        ).scalar_one_or_none()
        if correction is None or not correction.device_command_uuid:
            return []
        command = db.execute(
            select(DeviceCommand).where(DeviceCommand.command_uuid == correction.device_command_uuid)
        ).scalar_one_or_none()
        if command is None:
            return []
        return [
            DeviceVerificationRead(
                command_uuid=command.command_uuid,
                verification_status=command.verification_status,
                verification_details=command.verification_details,
                completed_at=command.completed_at,
            )
        ]

    commands = list(
        db.execute(
            select(DeviceCommand)
            .where(DeviceCommand.command_type == "CORRECT_ATTENDANCE")
            .order_by(DeviceCommand.completed_at.desc().nullslast())
            .limit(limit)
        ).scalars().all()
    )
    return [
        DeviceVerificationRead(
            command_uuid=c.command_uuid,
            verification_status=c.verification_status,
            verification_details=c.verification_details,
            completed_at=c.completed_at,
        )
        for c in commands
    ]


@router.get("/device-snapshots", response_model=list[DeviceSnapshotRead])
def list_device_snapshots(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator_account),
) -> list[DeviceStateSnapshot]:
    return list(
        db.execute(
            select(DeviceStateSnapshot).order_by(DeviceStateSnapshot.captured_at.desc()).limit(limit)
        ).scalars().all()
    )
