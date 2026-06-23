"""Employee HTTP routes."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.models.attendance_effective_punch import AttendanceEffectivePunch
from app.models.attendance_session import AttendanceSession
from app.models.device_user_mapping import DeviceUserMapping
from app.models.employee import Employee
from app.services.employee_identity import identity_filter_for_employee
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeDailyAttendanceRead,
    EmployeeDetailRead,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.audit_service import append_audit_log
from app.services.device_command_service import enqueue_device_command, process_command
from app.services.attendance_effective_service import (
    load_active_effective_punches,
    summarize_day_punches,
    summarize_employee_day_from_events,
)
from app.services.system_governance_service import assert_device_write_allowed

router = APIRouter(
    prefix="/employees",
    tags=["employees"],
    dependencies=[Depends(require_permissions(Permission.EMPLOYEE_VIEW))],
)


def _day_bounds_utc(d: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(d, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def _identity_filter_for_employee(emp: Employee, db: Session):
    return identity_filter_for_employee(emp, db)


def _rollover_device_mapping(
    db: Session,
    *,
    employee_uuid: str,
    device_id: str,
    device_user_id: str,
    effective_at: datetime,
) -> None:
    active_rows = db.execute(
        select(DeviceUserMapping).where(
            DeviceUserMapping.employee_uuid == employee_uuid,
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.active.is_(True),
        )
    ).scalars().all()
    for row in active_rows:
        if row.device_user_id == device_user_id:
            return
        row.active = False
        row.valid_to = effective_at
    conflicting_identity = db.execute(
        select(DeviceUserMapping).where(
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.device_user_id == device_user_id,
            DeviceUserMapping.active.is_(True),
        )
    ).scalars().all()
    for row in conflicting_identity:
        if row.employee_uuid != employee_uuid:
            row.active = False
            row.valid_to = effective_at
    db.add(
        DeviceUserMapping(
            employee_uuid=employee_uuid,
            device_id=device_id,
            device_user_id=device_user_id,
            valid_from=effective_at,
            active=True,
        )
    )


def _ensure_device_writes_enabled(db: Session, *, device_id: str) -> None:
    if get_settings().device_read_only:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device write operations are disabled (DEVICE_READ_ONLY=true).",
        )
    allowed, reason = assert_device_write_allowed(db, device_id=device_id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=reason or "Device writes blocked.")


@router.get("", response_model=list[EmployeeRead])
def list_employees(db: Session = Depends(get_db)) -> list[Employee]:
    return list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())


@router.get("/{employee_id}", response_model=EmployeeDetailRead)
def get_employee(employee_id: int, db: Session = Depends(get_db)) -> EmployeeDetailRead:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if not emp.employee_uuid:
        emp.employee_uuid = str(uuid4())
        db.commit()
        db.refresh(emp)

    total_logs = (
        db.execute(
            select(func.count())
            .select_from(AttendanceEffectivePunch)
            .where(AttendanceEffectivePunch.employee_id == emp.id, AttendanceEffectivePunch.is_active.is_(True))
        ).scalar_one()
        or 0
    )
    first_punch_at, last_punch_at = db.execute(
        select(func.min(AttendanceEffectivePunch.timestamp), func.max(AttendanceEffectivePunch.timestamp)).where(
            AttendanceEffectivePunch.employee_id == emp.id,
            AttendanceEffectivePunch.is_active.is_(True),
        )
    ).one()
    log_rows = list(
        db.execute(
            select(AttendanceEffectivePunch.timestamp, AttendanceEffectivePunch.punch_type)
            .where(AttendanceEffectivePunch.employee_id == emp.id, AttendanceEffectivePunch.is_active.is_(True))
            .order_by(AttendanceEffectivePunch.timestamp)
        )
    )
    tz = ZoneInfo(get_settings().timezone)
    days: dict[date, list[str]] = {}
    for ts, punch_type in log_rows:
        d = ts.astimezone(tz).date()
        days.setdefault(d, []).append(str(punch_type))
    total_attendance_days = len(days)
    total_complete_days = sum(1 for punches in days.values() if len(punches) > 1)

    return EmployeeDetailRead(
        id=emp.id,
        employee_uuid=emp.employee_uuid,
        device_user_id=emp.device_user_id,
        device_uid=emp.device_uid,
        device_privilege=emp.device_privilege,
        device_group_id=emp.device_group_id,
        device_card=emp.device_card,
        name=emp.name,
        department=emp.department,
        shift_start=emp.shift_start,
        shift_end=emp.shift_end,
        created_at=emp.created_at,
        total_logs=total_logs,
        first_punch_at=first_punch_at,
        last_punch_at=last_punch_at,
        total_attendance_days=total_attendance_days,
        total_complete_days=total_complete_days,
    )


@router.get("/{employee_id}/daily-attendance", response_model=list[EmployeeDailyAttendanceRead])
def get_employee_daily_attendance(
    employee_id: int,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> list[EmployeeDailyAttendanceRead]:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if not emp.employee_uuid:
        emp.employee_uuid = str(uuid4())
        db.commit()
        db.refresh(emp)

    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    local_today = datetime.now(tz).date()
    start_date = date_from or (local_today - timedelta(days=30))
    end_date = date_to or local_today
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'to' date must be on or after 'from' date",
        )

    effective_by_day: dict[date, list[AttendanceEffectivePunch]] = defaultdict(list)
    for punch in db.execute(
        select(AttendanceEffectivePunch).where(
            AttendanceEffectivePunch.employee_id == emp.id,
            AttendanceEffectivePunch.local_date >= start_date,
            AttendanceEffectivePunch.local_date <= end_date,
            AttendanceEffectivePunch.is_active.is_(True),
        ).order_by(AttendanceEffectivePunch.local_date, AttendanceEffectivePunch.timestamp)
    ).scalars().all():
        effective_by_day[punch.local_date].append(punch)

    rows: list[EmployeeDailyAttendanceRead] = []
    d = start_date
    while d <= end_date:
        punches = effective_by_day.get(d, [])
        if punches:
            first_in, last_out, total_work_minutes = summarize_day_punches(punches, tz_name=settings.timezone)
            punch_count = len(punches)
        else:
            first_in, last_out, total_work_minutes, punch_count = summarize_employee_day_from_events(
                db, employee=emp, local_date=d, settings=settings
            )
        if punch_count == 0:
            rows.append(
                EmployeeDailyAttendanceRead(
                    summary_date=d,
                    first_check_in=None,
                    last_check_out=None,
                    total_work_minutes=None,
                    absent=True,
                    punch_count=0,
                )
            )
        else:
            rows.append(
                EmployeeDailyAttendanceRead(
                    summary_date=d,
                    first_check_in=first_in,
                    last_check_out=last_out,
                    total_work_minutes=total_work_minutes,
                    absent=first_in is None and last_out is None,
                    punch_count=punch_count,
                )
            )
        d += timedelta(days=1)

    rows.sort(key=lambda r: r.summary_date, reverse=True)
    return rows


@router.post("", response_model=EmployeeRead)
def upsert_employee_metadata(
    payload: EmployeeCreate,
    request: Request,
    user: User = Depends(require_permissions(Permission.EMPLOYEE_EDIT)),
    db: Session = Depends(get_db),
) -> Employee:
    """
    Create or update employee metadata in DB only (does not push to device).
    device_user_id must match the terminal user id.
    """
    settings = get_settings()
    _ensure_device_writes_enabled(db, device_id=settings.zk_device_id)
    existing = db.execute(select(Employee).where(Employee.device_user_id == payload.device_user_id)).scalar_one_or_none()
    effective_at = datetime.now(ZoneInfo("UTC"))
    if existing is not None:
        previous = {
            "device_user_id": existing.device_user_id,
            "name": existing.name,
            "department": existing.department,
            "shift_start": existing.shift_start.isoformat() if existing.shift_start else None,
            "shift_end": existing.shift_end.isoformat() if existing.shift_end else None,
        }
        if not existing.employee_uuid:
            existing.employee_uuid = str(uuid4())
        existing.name = payload.name
        existing.department = payload.department
        existing.shift_start = payload.shift_start
        existing.shift_end = payload.shift_end
        _rollover_device_mapping(
            db,
            employee_uuid=existing.employee_uuid,
            device_id=settings.zk_device_id,
            device_user_id=payload.device_user_id,
            effective_at=effective_at,
        )
        command = enqueue_device_command(
            db,
            device_id=settings.zk_device_id,
            command_type="UPSERT_USER",
            payload={
                "user_id": payload.device_user_id,
                "name": payload.name,
                "uid": existing.device_uid,
                "privilege": existing.device_privilege,
                "group_id": existing.device_group_id,
                "card": existing.device_card,
            },
            correlation_id=getattr(request.state, "request_id", None),
            created_by=user.user_uuid,
            initiated_from="api:employees.upsert",
        )
        # Inline-safe processing fallback prevents queue buildup when workers lag/offline.
        process_command(db, command, settings=settings, worker_id="api-inline")
        append_audit_log(
            db,
            actor_user_uuid=user.user_uuid,
            action_type="EMPLOYEE_UPDATED",
            entity_type="employee",
            entity_id=existing.employee_uuid,
            previous_state=previous,
            new_state={
                "device_user_id": existing.device_user_id,
                "name": existing.name,
                "department": existing.department,
                "shift_start": existing.shift_start.isoformat() if existing.shift_start else None,
                "shift_end": existing.shift_end.isoformat() if existing.shift_end else None,
            },
            ip_address=request.client.host if request.client else None,
            request_id=getattr(request.state, "request_id", None),
        )
        db.commit()
        db.refresh(existing)
        return existing
    emp = Employee(
        employee_uuid=str(uuid4()),
        device_user_id=payload.device_user_id,
        name=payload.name,
        department=payload.department,
        shift_start=payload.shift_start,
        shift_end=payload.shift_end,
    )
    db.add(emp)
    db.flush()
    _rollover_device_mapping(
        db,
        employee_uuid=emp.employee_uuid,
        device_id=settings.zk_device_id,
        device_user_id=payload.device_user_id,
        effective_at=effective_at,
    )
    command = enqueue_device_command(
        db,
        device_id=settings.zk_device_id,
        command_type="UPSERT_USER",
        payload={
            "user_id": payload.device_user_id,
            "name": payload.name,
            "uid": emp.device_uid,
            "privilege": emp.device_privilege,
            "group_id": emp.device_group_id,
            "card": emp.device_card,
        },
        correlation_id=getattr(request.state, "request_id", None),
        created_by=user.user_uuid,
        initiated_from="api:employees.upsert",
    )
    # Inline-safe processing fallback prevents queue buildup when workers lag/offline.
    process_command(db, command, settings=settings, worker_id="api-inline")
    append_audit_log(
        db,
        actor_user_uuid=user.user_uuid,
        action_type="EMPLOYEE_CREATED",
        entity_type="employee",
        entity_id=emp.employee_uuid,
        new_state={
            "device_user_id": emp.device_user_id,
            "name": emp.name,
            "department": emp.department,
            "shift_start": emp.shift_start.isoformat() if emp.shift_start else None,
            "shift_end": emp.shift_end.isoformat() if emp.shift_end else None,
        },
        ip_address=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    db.refresh(emp)
    return emp


@router.put("/{employee_id}", response_model=EmployeeRead)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    request: Request,
    user: User = Depends(require_permissions(Permission.EMPLOYEE_EDIT)),
    db: Session = Depends(get_db),
) -> Employee:
    """
    Update employee metadata and propagate identity/name changes to device + DB references.
    """
    existing = db.get(Employee, employee_id)
    _ensure_device_writes_enabled(db, device_id=get_settings().zk_device_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    new_device_user_id = (payload.device_user_id if payload.device_user_id is not None else existing.device_user_id).strip()
    new_name = (payload.name if payload.name is not None else existing.name).strip()
    if not new_device_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="device_user_id cannot be empty")
    if not new_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name cannot be empty")

    conflict = db.execute(
        select(Employee).where(Employee.device_user_id == new_device_user_id, Employee.id != employee_id)
    ).scalar_one_or_none()
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"device_user_id '{new_device_user_id}' already exists.",
        )

    previous = {
        "device_user_id": existing.device_user_id,
        "name": existing.name,
        "department": existing.department,
        "shift_start": existing.shift_start.isoformat() if existing.shift_start else None,
        "shift_end": existing.shift_end.isoformat() if existing.shift_end else None,
    }
    settings = get_settings()
    if not existing.employee_uuid:
        existing.employee_uuid = str(uuid4())

    existing.device_user_id = new_device_user_id
    existing.name = new_name
    if "department" in payload.model_fields_set:
        existing.department = payload.department
    if "shift_start" in payload.model_fields_set:
        existing.shift_start = payload.shift_start
    if "shift_end" in payload.model_fields_set:
        existing.shift_end = payload.shift_end
    _rollover_device_mapping(
        db,
        employee_uuid=existing.employee_uuid,
        device_id=settings.zk_device_id,
        device_user_id=new_device_user_id,
        effective_at=datetime.now(ZoneInfo("UTC")),
    )
    command = enqueue_device_command(
        db,
        device_id=settings.zk_device_id,
        command_type="UPSERT_USER",
        payload={
            "user_id": new_device_user_id,
            "name": new_name,
            "uid": existing.device_uid,
            "privilege": existing.device_privilege,
            "group_id": existing.device_group_id,
            "card": existing.device_card,
        },
        correlation_id=getattr(request.state, "request_id", None),
        created_by=user.user_uuid,
        initiated_from="api:employees.update",
    )
    # Inline-safe processing fallback prevents queue buildup when workers lag/offline.
    process_command(db, command, settings=settings, worker_id="api-inline")
    append_audit_log(
        db,
        actor_user_uuid=user.user_uuid,
        action_type="EMPLOYEE_UPDATED",
        entity_type="employee",
        entity_id=existing.employee_uuid,
        previous_state=previous,
        new_state={
            "device_user_id": existing.device_user_id,
            "name": existing.name,
            "department": existing.department,
            "shift_start": existing.shift_start.isoformat() if existing.shift_start else None,
            "shift_end": existing.shift_end.isoformat() if existing.shift_end else None,
        },
        ip_address=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
    )

    db.commit()
    db.refresh(existing)
    return existing
