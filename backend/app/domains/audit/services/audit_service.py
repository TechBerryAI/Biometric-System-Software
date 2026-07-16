"""Audit event recording helpers."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.domains.audit.models.audit_event import AuditEvent
from app.domains.auth.models.user import User


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def record_audit_event(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    outcome: str = "success",
    metadata: dict | None = None,
    request: Request | None = None,
) -> AuditEvent:
    tenant_id = None
    if request is not None:
        ctx = getattr(request.state, "tenant_context", None)
        if ctx is not None:
            tenant_id = ctx.tenant_id
    request_id = getattr(getattr(request, "state", None), "request_id", None) if request else None
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_user_uuid=actor.user_uuid if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
        request_id=request_id,
        outcome=outcome,
        metadata_json=metadata,
    )
    db.add(event)
    db.flush()
    return event
