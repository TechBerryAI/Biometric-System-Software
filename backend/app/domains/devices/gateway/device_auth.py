"""Device HMAC authentication for push gateway."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Any

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.redis_keys import with_namespace
from app.core.security import hash_password
from app.domains.devices.models.device import Device

logger = logging.getLogger(__name__)

REPLAY_WINDOW_SECONDS = 300
NONCE_TTL_SECONDS = 600


def generate_device_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_device_secret(secret: str) -> str:
    return hash_password(secret)


def verify_device_secret(secret: str, secret_hash: str | None) -> bool:
    if not secret_hash:
        return False
    from app.core.security import verify_password

    return verify_password(secret, secret_hash)


def build_signature_payload(
    *,
    device_id: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{device_id}:{timestamp}:{nonce}:{body_hash}"
    return canonical.encode("utf-8")


def sign_request(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_request_signature(
    secret: str,
    payload: bytes,
    signature: str,
) -> bool:
    expected = sign_request(secret, payload)
    return hmac.compare_digest(expected, signature)


class DeviceAuthService:
    """Validates inbound push requests from biometric devices."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _redis(self) -> Redis | None:
        try:
            return Redis.from_url(str(self._settings.redis_url), decode_responses=True)
        except Exception:  # noqa: BLE001
            return None

    def _nonce_key(self, device_id: str, nonce: str) -> str:
        return with_namespace(self._settings.redis_namespace, f"device:nonce:{device_id}:{nonce}")

    def is_replay(self, device_id: str, nonce: str) -> bool:
        client = self._redis()
        if client is None:
            return False
        key = self._nonce_key(device_id, nonce)
        if client.get(key):
            return True
        client.setex(key, NONCE_TTL_SECONDS, "1")
        return False

    def authenticate_push_request(
        self,
        db: Session,
        *,
        device_id: str,
        timestamp: str,
        nonce: str,
        signature: str,
        body: bytes,
        device_secret: str | None = None,
    ) -> tuple[Device | None, str | None]:
        device = db.execute(
            select(Device).where(Device.name == device_id, Device.active.is_(True))
        ).scalar_one_or_none()
        if device is None:
            return None, "Unknown or inactive device."

        if device.connectivity_mode not in {"push", "both"}:
            return None, "Device is not configured for push connectivity."

        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return None, "Invalid timestamp."

        now = int(time.time())
        if abs(now - ts) > REPLAY_WINDOW_SECONDS:
            return None, "Request timestamp outside replay window."

        if self.is_replay(device_id, nonce):
            return None, "Replay detected: nonce already used."

        secret = device_secret
        if secret is None and device.device_secret_hash:
            return None, "Device secret required for signature verification."

        if secret is None:
            return None, "Device has no configured secret."

        if device.device_secret_hash and not verify_device_secret(secret, device.device_secret_hash):
            return None, "Invalid device credentials."

        payload = build_signature_payload(device_id=device_id, timestamp=timestamp, nonce=nonce, body=body)
        if not verify_request_signature(secret, payload, signature):
            return None, "Invalid request signature."

        return device, None


def rotate_device_secret(db: Session, device: Device) -> tuple[str, Device]:
    secret = generate_device_secret()
    device.device_secret_hash = hash_device_secret(secret)
    db.flush()
    return secret, device
