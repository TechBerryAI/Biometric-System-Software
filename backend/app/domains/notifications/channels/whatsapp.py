"""WhatsApp notification channel (stub)."""

from __future__ import annotations

import logging

from app.domains.notifications.channels.base import NotificationChannel, NotificationPayload

log = logging.getLogger(__name__)


class WhatsAppChannel(NotificationChannel):
    channel_name = "whatsapp"

    def send(self, payload: NotificationPayload) -> bool:
        log.info("notification.whatsapp.stub recipient=%s", payload.recipient)
        return True
