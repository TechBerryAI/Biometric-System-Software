"""Multi-channel notification orchestration."""

from __future__ import annotations

import logging

from app.domains.notifications.channels import (
    EmailChannel,
    NotificationChannel,
    NotificationPayload,
    SmsChannel,
    WebhookChannel,
    WhatsAppChannel,
)

log = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, channels: dict[str, NotificationChannel] | None = None) -> None:
        self._channels = channels or {
            "email": EmailChannel(),
            "sms": SmsChannel(),
            "whatsapp": WhatsAppChannel(),
            "webhook": WebhookChannel(),
        }

    def send(self, channel: str, payload: NotificationPayload) -> bool:
        handler = self._channels.get(channel)
        if handler is None:
            log.warning("notification.unknown_channel channel=%s", channel)
            return False
        return handler.send(payload)

    def broadcast(self, channels: list[str], payload: NotificationPayload) -> dict[str, bool]:
        return {name: self.send(name, payload) for name in channels}
