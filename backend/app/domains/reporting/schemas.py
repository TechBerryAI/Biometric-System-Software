"""Reporting API schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class HeatmapCell(BaseModel):
    day: date
    hour: int = Field(ge=0, le=23)
    punch_count: int = Field(ge=0)


class AttendanceHeatmapResponse(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    cells: list[HeatmapCell] = Field(default_factory=list)


class BranchComparisonRow(BaseModel):
    branch_id: str
    branch_name: str
    headcount: int
    present_rate: float
    late_rate: float
    avg_work_hours: float


class BranchComparisonResponse(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    branches: list[BranchComparisonRow] = Field(default_factory=list)


class DeviceUptimeRow(BaseModel):
    device_uuid: str
    device_name: str
    uptime_percent: float
    last_seen: datetime | None
    health_status: str


class DeviceUptimeResponse(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    devices: list[DeviceUptimeRow] = Field(default_factory=list)
