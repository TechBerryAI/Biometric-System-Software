"""Unit tests for the dedicated password-reset SMTP sender."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.domains.auth.services.password_reset_mailer import (
    _html_reset_email,
    send_password_reset_email,
)


@pytest.mark.testid("BE-UNIT-MAIL-001")
def test_send_password_reset_email_skips_when_smtp_unconfigured() -> None:
    get_settings.cache_clear()
    assert send_password_reset_email(recipient="admin@example.com", otp="123456") is False


@pytest.mark.testid("BE-UNIT-MAIL-001")
def test_html_reset_email_includes_otp_not_a_link() -> None:
    body = _html_reset_email(recipient_name="Rahul", otp="847291", expire_minutes=60)
    assert "847291" in body or "8 4 7 2 9 1" in body
    assert "Rahul" in body
    assert "reset-password?token=" not in body
    assert "Biometric Attendance System" in body


@pytest.mark.testid("BE-UNIT-MAIL-001")
def test_send_password_reset_email_uses_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    monkeypatch.setenv("SMTP_USER", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    get_settings.cache_clear()

    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("app.domains.auth.services.password_reset_mailer.smtplib.SMTP", return_value=smtp) as smtp_cls:
        sent = send_password_reset_email(
            recipient="admin@example.com",
            otp="123456",
            recipient_name="Admin User",
        )

    assert sent is True
    smtp_cls.assert_called_once()
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("mailer", "secret")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert message["Subject"] == "Your password reset code"
    get_settings.cache_clear()
