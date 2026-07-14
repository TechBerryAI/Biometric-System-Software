"""Unit tests for authentication service helpers."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domains.auth.services.auth_service import LoginRateLimiter, authenticate_user
from tests.factories import make_user


@pytest.mark.testid("BE-UNIT-AUTH-001")
def test_hash_and_verify_password() -> None:
    hashed = hash_password("Secret123!")
    assert hashed != "Secret123!"
    assert verify_password("Secret123!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


@pytest.mark.testid("BE-UNIT-AUTH-001")
@pytest.mark.testid("BE-UNIT-AUTH-010")
def test_login_rate_limiter_not_blocked_without_redis() -> None:
    limiter = LoginRateLimiter()
    limiter._redis = None
    assert limiter.is_blocked("anyone@example.com") is False
    limiter.register_failure("anyone@example.com")
    # Without Redis, failures are best-effort no-ops and auth stays open.
    assert limiter.is_blocked("anyone@example.com") is False


@pytest.mark.testid("BE-UNIT-AUTH-001")
def test_authenticate_user_with_db_session(db_session: Session) -> None:
    user = make_user(email="auth-unit@example.com", password="Secret123!")
    db_session.add(user)
    db_session.commit()

    ok = authenticate_user(db_session, "auth-unit@example.com", "Secret123!")
    assert ok is not None
    assert ok.email == "auth-unit@example.com"

    assert authenticate_user(db_session, "auth-unit@example.com", "bad") is None
    assert authenticate_user(db_session, "missing@example.com", "Secret123!") is None
