"""Pydantic schemas for employees."""

from __future__ import annotations

from datetime import datetime, time

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
    created_at: datetime
