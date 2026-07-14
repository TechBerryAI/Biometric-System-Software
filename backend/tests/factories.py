"""Shared test factories for domain objects."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.security import hash_password
from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_command import DeviceCommand, DeviceCommandStatus
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.employees.models.employee import Employee
from app.domains.ops.models.system_control_state import SystemControlState
from app.domains.auth.models.user import User, UserRole

UTC = ZoneInfo("UTC")


def make_user(
    *,
    email: str = "admin@example.com",
    password: str = "Secret123!",
    role: str = UserRole.SUPER_ADMIN.value,
    account_flags: int = 0,
    active: bool = True,
    full_name: str | None = "Test Admin",
) -> User:
    return User(
        email=email.strip().lower(),
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
        account_flags=account_flags,
        active=active,
    )


def make_operator(*, email: str = "operator@example.com", password: str = "Secret123!") -> User:
    return make_user(email=email, password=password, role=UserRole.SUPER_ADMIN.value, account_flags=1)


def make_employee(
    *,
    device_user_id: str | None = None,
    name: str = "Test Employee",
    department: str | None = "Engineering",
    shift_start: time | None = time(9, 0),
    shift_end: time | None = time(18, 0),
    device_uid: int | None = 1,
) -> Employee:
    return Employee(
        device_user_id=device_user_id or f"TBI{uuid4().hex[:6].upper()}",
        name=name,
        department=department,
        shift_start=shift_start,
        shift_end=shift_end,
        device_uid=device_uid,
    )


def make_device(
    *,
    name: str = "Main Entrance",
    ip_address: str = "192.168.1.200",
    port: int = 4370,
    health_status: str = "ONLINE",
    mode: str = "NORMAL",
) -> Device:
    return Device(
        name=name,
        ip_address=ip_address,
        port=port,
        health_status=health_status,
        mode=mode,
        active=True,
    )


def make_mapping(
    *,
    employee: Employee,
    device_id: str = "main-entrance",
    device_user_id: str | None = None,
    active: bool = True,
) -> DeviceUserMapping:
    return DeviceUserMapping(
        employee_uuid=employee.employee_uuid,
        device_id=device_id,
        device_user_id=device_user_id or employee.device_user_id,
        active=active,
    )


def make_attendance_log(
    *,
    employee: Employee,
    punched_at: datetime | None = None,
    punch_type: str = "0",
    device_id: str = "main-entrance",
) -> AttendanceLog:
    ts = punched_at or datetime.now(UTC)
    return AttendanceLog(
        employee_code=employee.device_user_id,
        timestamp=ts,
        device_id=device_id,
        employee_uuid=employee.employee_uuid,
        punch_type=punch_type,
    )


def make_device_command(
    *,
    device_id: str = "main-entrance",
    command_type: str = "UPSERT_USER",
    payload: dict | None = None,
    status: str = DeviceCommandStatus.PENDING.value,
    idempotency_key: str | None = None,
) -> DeviceCommand:
    return DeviceCommand(
        command_uuid=str(uuid4()),
        device_id=device_id,
        command_type=command_type,
        payload=payload or {"user_id": "TBI001", "name": "Test"},
        status=status,
        idempotency_key=idempotency_key or uuid4().hex,
        retries=0,
    )


def make_control_state(
    *,
    maintenance_mode: bool = False,
    emergency_freeze_mode: bool = False,
) -> SystemControlState:
    return SystemControlState(
        singleton_key="global",
        maintenance_mode=maintenance_mode,
        emergency_freeze_mode=emergency_freeze_mode,
    )


def day_bounds(d: date | None = None) -> tuple[datetime, datetime]:
    local = d or date.today()
    start = datetime(local.year, local.month, local.day, tzinfo=UTC)
    return start, start + timedelta(days=1)
