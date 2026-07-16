"""Unit tests for NotificationService."""

from __future__ import annotations

import pytest

from app.domains.notifications.channels.base import NotificationPayload
from app.domains.notifications.notification_service import NotificationService


@pytest.mark.testid("BE-UNIT-NOTIF-001")
def test_notification_service_sends_email_stub() -> None:
    service = NotificationService()
    ok = service.send(
        "email",
        NotificationPayload(recipient="hr@example.com", subject="Alert", body="Test message"),
    )
    assert ok is True


@pytest.mark.testid("BE-UNIT-NOTIF-002")
def test_notification_service_unknown_channel_returns_false() -> None:
    service = NotificationService()
    ok = service.send("pager", NotificationPayload(recipient="+10000000000", body="noop"))
    assert ok is False
