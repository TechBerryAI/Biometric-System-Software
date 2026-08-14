"""Email notification channel (stub)."""

from __future__ import annotations

import logging

from app.domains.notifications.channels.base import NotificationChannel, NotificationPayload

log = logging.getLogger(__name__)


class EmailChannel(NotificationChannel):
    channel_name = "email"

    def send(self, payload: NotificationPayload) -> bool:
        log.info(
            "notification.email.stub recipient=%s subject=%s",
            payload.recipient,
            payload.subject or "(no subject)",
        )
        return True
