"""Feature flags from env defaults + per-tenant JSON overrides."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Built-in defaults (env FEATURE_FLAGS_* can override via Settings).
DEFAULT_FLAGS: dict[str, bool] = {
    "ai_insights": True,
    "dashboard_cache": True,
    "attendance_archive": True,
    "device_auto_reconcile": True,
    "push_gateway": True,
    "mfa_enforcement": False,
    "buddy_punch_detection": True,
}


class FeatureFlags:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _env_overrides(self) -> dict[str, bool]:
        raw = (self._settings.feature_flags or "").strip()
        if not raw:
            return {}
        out: dict[str, bool] = {}
        for part in raw.split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, value = part.split("=", 1)
            out[name.strip()] = value.strip().lower() in {"1", "true", "yes", "on"}
        return out

    def defaults(self) -> dict[str, bool]:
        flags = dict(DEFAULT_FLAGS)
        flags.update(self._env_overrides())
        return flags

    def for_tenant(self, db: Session | None, tenant_id: int | None) -> dict[str, bool]:
        flags = self.defaults()
        if db is None or tenant_id is None:
            return flags
        try:
            from app.domains.tenancy.models.hierarchy import Tenant

            tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none()
            if tenant and isinstance(tenant.features, dict):
                for key, value in tenant.features.items():
                    if isinstance(value, bool):
                        flags[str(key)] = value
        except Exception as exc:  # noqa: BLE001
            logger.debug("feature_flags.tenant_lookup_failed: %s", exc)
        return flags

    def is_enabled(
        self,
        name: str,
        *,
        db: Session | None = None,
        tenant_id: int | None = None,
        default: bool | None = None,
    ) -> bool:
        flags = self.for_tenant(db, tenant_id)
        if name in flags:
            return bool(flags[name])
        if default is not None:
            return default
        return bool(DEFAULT_FLAGS.get(name, False))

    def snapshot(self, db: Session | None = None, tenant_id: int | None = None) -> dict[str, Any]:
        return {"flags": self.for_tenant(db, tenant_id), "tenant_id": tenant_id}


_flags: FeatureFlags | None = None


def get_feature_flags(settings: Settings | None = None) -> FeatureFlags:
    global _flags
    if _flags is None:
        _flags = FeatureFlags(settings=settings)
    return _flags


def reset_feature_flags() -> None:
    global _flags
    _flags = None
