"""Unit tests for production config validation."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.config_validation import validate_production_config


def test_production_validation_skipped_in_development() -> None:
    settings = Settings(
        ENVIRONMENT="development",
        JWT_SECRET_KEY="change-me",
        AUTH_ENABLED=True,
        ENCRYPTION_KEY=None,
    )
    validate_production_config(settings)


def test_production_validation_fails_on_insecure_jwt() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="change-me",
        AUTH_ENABLED=False,
        ENCRYPTION_KEY="test-key",
        DATABASE_URL="postgresql+psycopg://u:p@db:5432/biometric",
        REDIS_URL="redis://redis:6379/0",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_production_config(settings)


def test_production_validation_requires_encryption_key() -> None:
    settings = Settings(
        ENVIRONMENT="staging",
        JWT_SECRET_KEY="super-secret-production-key",
        AUTH_ENABLED=True,
        ENCRYPTION_KEY=None,
        DATABASE_URL="postgresql+psycopg://u:p@db:5432/biometric",
        REDIS_URL="redis://redis:6379/0",
    )
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        validate_production_config(settings)
