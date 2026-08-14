"""Audit domain services."""

from app.domains.audit.services.audit_service import record_audit_event

__all__ = ["record_audit_event"]
