"""Unit tests for authentication service helpers."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domains.auth.models.password_reset_token import PasswordResetToken
from app.domains.auth.services.auth_service import (
    LoginRateLimiter,
    authenticate_user,
    hash_password_reset_otp,
    request_password_reset,
    reset_password_with_otp,
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
        missing = request_password_reset(db_session, "missing@example.com")
        viewer_result = request_password_reset(db_session, viewer.email)
        db_session.commit()

    assert missing is False
    assert viewer_result is False
    send_mail.assert_not_called()
    assert db_session.query(PasswordResetToken).count() == 0


@pytest.mark.testid("BE-UNIT-AUTH-001")
def test_request_password_reset_sends_only_for_existing_account(db_session: Session) -> None:
    from unittest.mock import patch

    user = make_user(email="reset-exists@example.com", password="Secret123!")
    db_session.add(user)
    db_session.commit()

    with patch("app.domains.auth.services.auth_service.send_password_reset_email") as send_mail:
        issued = request_password_reset(db_session, user.email)
        db_session.commit()

    assert issued is True
    send_mail.assert_called_once()
    assert send_mail.call_args.kwargs["recipient"] == user.email
    otp = send_mail.call_args.kwargs["otp"]
    assert otp.isdigit() and len(otp) == 6
    assert db_session.query(PasswordResetToken).count() == 1


@pytest.mark.testid("BE-UNIT-AUTH-001")
def test_reset_password_with_otp_rejects_expired(db_session: Session) -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    user = make_user(email="reset-unit@example.com", password="Secret123!")
    db_session.add(user)
    db_session.flush()
    otp = "123456"
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_otp(user.id, otp),
            expires_at=datetime.now(ZoneInfo("UTC")) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    assert reset_password_with_otp(db_session, user.email, otp, "NewSecret123!") is None
    assert authenticate_user(db_session, user.email, "Secret123!") is not None
