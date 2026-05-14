"""Schemas for device command queue visibility."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeviceCommandRead(BaseModel):
    command_uuid: str
    device_id: str
    command_type: str
    status: str
    retries: int
    last_error: str | None
    correlation_id: str | None
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
