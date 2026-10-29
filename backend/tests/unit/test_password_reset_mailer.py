"""Unit tests for the dedicated password-reset SMTP sender."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.domains.auth.services.password_reset_mailer import send_password_reset_email


@pytest.mark.testid("BE-UNIT-MAIL-001")
def test_send_password_reset_email_skips_when_smtp_unconfigured() -> None:
    get_settings.cache_clear()
    assert send_password_reset_email(recipient="admin@example.com", reset_url="http://localhost/reset") is False


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
            reset_url="http://localhost:5173/reset-password?token=abc",
        )

    assert sent is True
    smtp_cls.assert_called_once()
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("mailer", "secret")
    smtp.send_message.assert_called_once()
    get_settings.cache_clear()
