"""Notification channel interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    recipient: str
    body: str
    subject: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class NotificationChannel(ABC):
    channel_name: str

    @abstractmethod
    def send(self, payload: NotificationPayload) -> bool:
        """Deliver notification; return True when accepted for delivery."""
