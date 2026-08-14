"""Fail-fast validation for production deployments."""

from __future__ import annotations

from app.core.config import Settings

_INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "change-me",
        "replace-this-in-production",
        "local-test-secret",
        "test-jwt-secret-key-not-for-prod",
    }
)


def is_production_like(settings: Settings) -> bool:
    return settings.environment.lower() in {"production", "prod", "staging"}


def validate_production_config(settings: Settings) -> None:
    """Raise RuntimeError when required secrets are missing in prod/staging."""
    if not is_production_like(settings):
        return

    errors: list[str] = []

    if settings.jwt_secret_key.strip().lower() in _INSECURE_JWT_SECRETS:
        errors.append("JWT_SECRET_KEY must be set to a strong secret in production/staging")

    if settings.auth_enabled and not settings.encryption_key:
        errors.append("ENCRYPTION_KEY is required when AUTH_ENABLED=true in production/staging")

    if not settings.database_url:
        errors.append("DATABASE_URL (or DB_* fields) must be configured in production/staging")

    if settings.redis_url.startswith("redis://localhost") and settings.environment.lower() == "production":
        errors.append("REDIS_URL should not point at localhost in production")

    if errors:
        joined = "; ".join(errors)
        raise RuntimeError(f"Production configuration validation failed: {joined}")
