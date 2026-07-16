"""Notification channels package."""

from app.domains.notifications.channels.base import NotificationChannel, NotificationPayload
from app.domains.notifications.channels.email import EmailChannel
from app.domains.notifications.channels.sms import SmsChannel
from app.domains.notifications.channels.webhook import WebhookChannel
from app.domains.notifications.channels.whatsapp import WhatsAppChannel

__all__ = [
    "NotificationChannel",
    "NotificationPayload",
    "EmailChannel",
    "SmsChannel",
    "WhatsAppChannel",
    "WebhookChannel",
]
