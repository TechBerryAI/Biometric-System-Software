"""Dedicated SMTP sender for password-reset emails."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger(__name__)


def send_password_reset_email(*, recipient: str, reset_url: str) -> bool:
    settings = get_settings()
    host = (settings.smtp_host or "").strip()
    from_addr = (settings.smtp_from or "").strip()
    if not host or not from_addr:
        log.warning("password_reset.email.skipped reason=smtp_not_configured recipient=%s", recipient)
        return False

    expire_minutes = settings.password_reset_expire_minutes
    message = EmailMessage()
    message["Subject"] = "Reset your password"
    message["From"] = from_addr
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for this account.\n"
        f"Open this link to choose a new password (expires in {expire_minutes} minutes):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email.\n"
    )

    try:
        with smtplib.SMTP(host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
    except Exception:
        log.exception("password_reset.email.failed recipient=%s", recipient)
        return False

    log.info("password_reset.email.sent recipient=%s", recipient)
    return True
