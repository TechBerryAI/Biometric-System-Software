"""Audit log response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    actor_user_uuid: str | None
    action_type: str
    entity_type: str
    entity_id: str
    previous_state: dict[str, Any] | None
    new_state: dict[str, Any] | None
    ip_address: str | None
    request_id: str | None
    metadata_json: dict[str, Any] | None
    timestamp: datetime
