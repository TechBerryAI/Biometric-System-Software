"""Shared employee identity filters for attendance queries."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domains.attendance.models.attendance_log import AttendanceLog
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.employees.models.employee import Employee


def identity_filter_for_employee(emp: Employee, db: Session):
    mapped_codes = {
        row[0]
        for row in db.execute(
            select(DeviceUserMapping.device_user_id).where(DeviceUserMapping.employee_uuid == emp.employee_uuid)
        ).all()
        if row[0]
    }
    mapped_codes.add(emp.device_user_id)
    return or_(
        AttendanceLog.employee_uuid == emp.employee_uuid,
        and_(AttendanceLog.employee_uuid.is_(None), AttendanceLog.employee_code.in_(mapped_codes)),
    )
