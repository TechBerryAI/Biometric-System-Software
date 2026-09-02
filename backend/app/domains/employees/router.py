"""Employee HTTP routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, Response
from fastapi import HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import device_policy
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import Permission, require_permissions
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.employees.models.employee import Employee
from app.domains.auth.models.user import User
from app.domains.employees.schemas import (
    EmployeeCreate,
    EmployeeDailyAttendanceRead,
    EmployeeDetailRead,
    EmployeeRead,
    EmployeeUpdate,
)
from app.domains.devices.services.device_command_service import enqueue_device_command, process_command
from app.domains.employees.services.employee_offboard_service import offboard_employee
from app.domains.attendance.services.attendance_helpers import (
    employee_punch_bounds,
    load_raw_punches_for_dates,
    summarize_employee_day_from_logs,
)
from app.domains.ops.services.system_governance_service import assert_device_write_allowed
from app.shared.ids import new_employee_id

router = APIRouter(
    prefix="/employees",
    tags=["employees"],
    dependencies=[Depends(require_permissions(Permission.EMPLOYEE_VIEW))],
)


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
    if not device_policy.DEVICE_WRITES_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device write operations are disabled by policy.",
        )
    allowed, reason = assert_device_write_allowed(db, device_id=device_id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=reason or "Device writes blocked.")


@router.get("", response_model=list[EmployeeRead])
def list_employees(db: Session = Depends(get_db)) -> list[Employee]:
    return list(
        db.execute(
            select(Employee).where(Employee.departed_at.is_(None)).order_by(Employee.id)
        ).scalars().all()
    )


@router.get("/{employee_id}", response_model=EmployeeDetailRead)
def get_employee(employee_id: int, db: Session = Depends(get_db)) -> EmployeeDetailRead:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.departed_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if not emp.employee_uuid:
        emp.employee_uuid = new_employee_id()
        db.commit()
        db.refresh(emp)

    employee_code = str(emp.device_user_id)
    total_logs = (
        db.execute(
            select(func.count())
            .select_from(AttendanceLog)
            .where(AttendanceLog.employee_code == employee_code)
        ).scalar_one()
        or 0
    )
    first_punch_at, last_punch_at = employee_punch_bounds(db, employee=emp)
    log_rows = list(
        db.execute(
            select(AttendanceLog.timestamp, AttendanceLog.punch_type)
            .where(AttendanceLog.employee_code == employee_code)
            .order_by(AttendanceLog.timestamp)
        )
    )
    tz = ZoneInfo(get_settings().resolved_timezone())
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
    if emp is None or emp.departed_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if not emp.employee_uuid:
        emp.employee_uuid = new_employee_id()
        db.commit()
        db.refresh(emp)

    settings = get_settings()
    tz = ZoneInfo(settings.resolved_timezone())
    local_today = datetime.now(tz).date()
    start_date = date_from or (local_today - timedelta(days=30))
    end_date = date_to or local_today
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'to' date must be on or after 'from' date",
        )

    raw_by_day = load_raw_punches_for_dates(
        db, start_date=start_date, end_date=end_date, employees=[emp], settings=settings
    )

    rows: list[EmployeeDailyAttendanceRead] = []
    d = start_date
    while d <= end_date:
        first_in, last_out, total_work_minutes, punch_count = summarize_employee_day_from_logs(
            db,
            employee=emp,
            local_date=d,
            settings=settings,
            logs=raw_by_day.get(d, {}).get(emp.id),
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
    Create or update employee metadata. Device upsert runs only for new employees
    or when the display name changes (department/shift are DB-only).
    device_user_id must match the terminal user id.
    """
    settings = get_settings()
    existing = db.execute(select(Employee).where(Employee.device_user_id == payload.device_user_id)).scalar_one_or_none()
    effective_at = datetime.now(ZoneInfo("UTC"))
    if existing is not None:
        if not existing.employee_uuid:
            existing.employee_uuid = new_employee_id()
        name_changed = existing.name.strip() != payload.name.strip()
        if name_changed:
            _ensure_device_writes_enabled(db, device_id=settings.zk_device_id)
        existing.departed_at = None
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
        if name_changed:
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
        db.commit()
        db.refresh(existing)
        return existing
    _ensure_device_writes_enabled(db, device_id=settings.zk_device_id)
    emp = Employee(
        employee_uuid=new_employee_id(),
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
    Department/shift-only updates stay in DB (those fields are not stored on the terminal).
    """
    existing = db.get(Employee, employee_id)
    if existing is None or existing.departed_at is not None:
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

    settings = get_settings()
    if not existing.employee_uuid:
        existing.employee_uuid = new_employee_id()

    identity_changed = (
        existing.device_user_id.strip() != new_device_user_id
        or existing.name.strip() != new_name
    )
    if identity_changed:
        _ensure_device_writes_enabled(db, device_id=settings.zk_device_id)
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
    if identity_changed:
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

    db.commit()
    db.refresh(existing)
    return existing


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def offboard_employee_route(
    employee_id: int,
    request: Request,
    user: User = Depends(require_permissions(Permission.EMPLOYEE_EDIT)),
    db: Session = Depends(get_db),
) -> Response:
    """Soft-offboard an employee: hide from directory and remove from biometric device."""
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if emp.departed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee is already offboarded.")

    settings = get_settings()
    _ensure_device_writes_enabled(db, device_id=settings.zk_device_id)
    offboard_employee(
        db,
        emp,
        actor_user_uuid=user.user_uuid,
        reason="api_offboard",
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client else None,
        process_device_inline=True,
        settings=settings,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
