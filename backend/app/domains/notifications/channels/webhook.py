"""Webhook notification channel (stub)."""

from __future__ import annotations

import logging

from app.domains.notifications.channels.base import NotificationChannel, NotificationPayload

log = logging.getLogger(__name__)


class WebhookChannel(NotificationChannel):
    channel_name = "webhook"

    def __init__(self, *, target_url: str | None = None) -> None:
        self._target_url = target_url

    def send(self, payload: NotificationPayload) -> bool:
        log.info(
            "notification.webhook.stub recipient=%s target=%s",
            payload.recipient,
            self._target_url or payload.metadata.get("webhook_url", "unset"),
        )
        return True
