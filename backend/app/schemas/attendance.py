"""Pydantic schemas for attendance logs and sessions."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AttendanceLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    timestamp: datetime
    device_id: str
    punch_type: str
    created_at: datetime


class AttendanceSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    check_in: datetime
    check_out: datetime | None
    work_duration: int | None = Field(None, description="Minutes worked for this session")
    late_minutes: int | None
    early_minutes: int | None
    status: str
    created_at: datetime


class DailySummaryRow(BaseModel):
    summary_date: date
    employee_id: int
    device_user_id: int
    employee_name: str
    first_check_in: datetime | None
    last_check_out: datetime | None
    total_work_minutes: int | None
    late_arrival: bool
    sessions_count: int
