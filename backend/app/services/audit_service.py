"""Helpers for immutable audit logging."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def append_audit_log(
    db: Session,
    *,
    actor_user_uuid: str | None,
    action_type: str,
    entity_type: str,
    entity_id: str,
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_user_uuid=actor_user_uuid,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_state=previous_state,
        new_state=new_state,
        ip_address=ip_address,
        request_id=request_id,
        metadata_json=metadata_json,
    )
    db.add(row)
    return row
