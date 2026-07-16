"""SMS notification channel (stub)."""

from __future__ import annotations

import logging

from app.domains.notifications.channels.base import NotificationChannel, NotificationPayload

log = logging.getLogger(__name__)


class SmsChannel(NotificationChannel):
    channel_name = "sms"

    def send(self, payload: NotificationPayload) -> bool:
        log.info("notification.sms.stub recipient=%s", payload.recipient)
        return True
