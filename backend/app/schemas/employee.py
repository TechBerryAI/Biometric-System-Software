"""Pydantic schemas for employees."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class EmployeeBase(BaseModel):
    device_user_id: str = Field(..., description="Device user id from biometric terminal (authoritative)")
    name: str
    department: str | None = None
    shift_start: time | None = None
    shift_end: time | None = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    name: str | None = None
    department: str | None = None
    shift_start: time | None = None
    shift_end: time | None = None


class EmployeeRead(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_uid: int | None = None
    device_privilege: int | None = None
    device_group_id: str | None = None
    device_card: str | None = None
    created_at: datetime


class EmployeeDetailRead(EmployeeRead):
    total_logs: int
    first_punch_at: datetime | None
    last_punch_at: datetime | None
    total_attendance_days: int
    total_complete_days: int


class EmployeeDailyAttendanceRead(BaseModel):
    summary_date: date
    first_check_in: datetime | None
    last_check_out: datetime | None
    total_work_minutes: int | None
    late_arrival: bool
    absent: bool
    punch_count: int
