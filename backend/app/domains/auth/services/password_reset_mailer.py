"""Dedicated SMTP sender for password-reset OTP emails."""

from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger(__name__)


def _plain_reset_email(*, recipient_name: str, otp: str, expire_minutes: int) -> str:
    return (
        f"Hello {recipient_name},\n\n"
        "We received a request to reset your Biometric Attendance System password.\n"
        f"Use this one-time verification code in the app. It expires in {expire_minutes} minutes:\n\n"
        f"    {otp}\n\n"
        "Enter the code on the Reset password screen, then choose a new password.\n"
        "If you did not request this, you can ignore this email. Your password will stay the same.\n\n"
        "— Biometric Attendance System\n"
    )


def _html_reset_email(*, recipient_name: str, otp: str, expire_minutes: int) -> str:
    safe_name = html.escape(recipient_name)
    safe_otp = html.escape(otp)
    spaced_otp = " ".join(safe_otp)
    return f"""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Password reset code</title>
  </head>
  <body style="margin:0;padding:0;background:#eef2f7;font-family:Georgia,'Times New Roman',serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f7;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#0f172a;border-radius:18px;overflow:hidden;box-shadow:0 18px 50px rgba(15,23,42,0.18);">
            <tr>
              <td style="height:4px;background:linear-gradient(90deg,#4f46e5,#7c3aed,#10b981);"></td>
            </tr>
            <tr>
              <td style="padding:36px 40px 16px 40px;">
                <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:#94a3b8;">
                  Biometric Attendance System
                </p>
                <h1 style="margin:14px 0 0 0;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.25;color:#f8fafc;font-weight:normal;">
                  Your secure reset code
                </h1>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 40px 8px 40px;">
                <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.7;color:#cbd5e1;">
                  Hello {safe_name},
                </p>
                <p style="margin:14px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.7;color:#cbd5e1;">
                  A password reset was requested for your management account. Enter this one-time code in the app to choose a new password.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 40px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111827;border:1px solid #1e293b;border-radius:14px;">
                  <tr>
                    <td align="center" style="padding:28px 16px;">
                      <p style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#94a3b8;">
                        Verification code
                      </p>
                      <p style="margin:0;font-family:'Courier New',Courier,monospace;font-size:36px;letter-spacing:0.28em;color:#f8fafc;font-weight:bold;">
                        {spaced_otp}
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:0 40px 12px 40px;">
                <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.6;color:#94a3b8;">
                  This code expires in <strong style="color:#e2e8f0;">{expire_minutes} minutes</strong> and can be used once.
                  Open <em>Forgot password</em> in the app, then enter the code with your new password.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 40px 36px 40px;">
                <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:#64748b;">
                  If you did not request a reset, ignore this email. Your password will not change.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 40px;background:#0b1220;border-top:1px solid #1e293b;">
                <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:0.08em;color:#64748b;">
                  Confidential · Biometric Attendance System
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_password_reset_email(*, recipient: str, otp: str, recipient_name: str | None = None) -> bool:
    settings = get_settings()
    host = (settings.smtp_host or "").strip()
    from_addr = (settings.smtp_from or "").strip()
    if not host or not from_addr:
        log.warning("password_reset.email.skipped reason=smtp_not_configured recipient=%s", recipient)
        return False

    expire_minutes = settings.password_reset_expire_minutes
    display_name = (recipient_name or "").strip() or "there"
    message = EmailMessage()
    message["Subject"] = "Your password reset code"
    message["From"] = from_addr
    message["To"] = recipient
    message.set_content(_plain_reset_email(recipient_name=display_name, otp=otp, expire_minutes=expire_minutes))
    message.add_alternative(
        _html_reset_email(recipient_name=display_name, otp=otp, expire_minutes=expire_minutes),
        subtype="html",
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
