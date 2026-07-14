"""Schemas for device command queue visibility."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeviceCommandRead(BaseModel):
    id: int
    command_uuid: str
    device_id: str
    command_type: str
    status: str
    retries: int
    retry_backoff_seconds: int
    last_error: str | None
    correlation_id: str | None
    initiated_by: str | None
    initiated_from: str | None
    verification_status: str | None
    verification_details: dict | None
    firmware_profile: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    heartbeat_at: datetime | None
