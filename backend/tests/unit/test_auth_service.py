"""Unit tests for authentication service helpers."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.core.security import generate_refresh_token, hash_refresh_token
from app.domains.auth.models.password_reset_token import PasswordResetToken
from app.domains.auth.services.auth_service import (
    LoginRateLimiter,
    authenticate_user,
    request_password_reset,
    reset_password_with_token,
)
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


@pytest.mark.testid("BE-UNIT-AUTH-001")
def test_request_password_reset_skips_unknown_and_viewer(db_session: Session) -> None:
    from unittest.mock import patch

    viewer = make_user(email="viewer-reset@example.com", role="VIEWER")
    db_session.add(viewer)
    db_session.commit()

    with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
        request_password_reset(db_session, "missing@example.com")
        request_password_reset(db_session, viewer.email)
        db_session.commit()

    send_mail.assert_not_called()
    assert db_session.query(PasswordResetToken).count() == 0


@pytest.mark.testid("BE-UNIT-AUTH-001")
def test_reset_password_with_token_rejects_expired(db_session: Session) -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    user = make_user(email="reset-unit@example.com", password="Secret123!")
    db_session.add(user)
    db_session.flush()
    raw = generate_refresh_token()
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(ZoneInfo("UTC")) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    assert reset_password_with_token(db_session, raw, "NewSecret123!") is None
    assert authenticate_user(db_session, user.email, "Secret123!") is not None
