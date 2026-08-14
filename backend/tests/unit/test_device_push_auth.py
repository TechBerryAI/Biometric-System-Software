"""Device push gateway authentication tests."""

from __future__ import annotations

import time

from app.domains.devices.gateway.device_auth import (
    DeviceAuthService,
    build_signature_payload,
    generate_device_secret,
    hash_device_secret,
    sign_request,
)
from tests.factories import make_device


def test_sign_and_verify_request():
    secret = generate_device_secret()
    body = b'{"attendance":[]}'
    payload = build_signature_payload(
        device_id="push-device",
        timestamp=str(int(time.time())),
        nonce="nonce-1",
        body=body,
    )
    sig = sign_request(secret, payload)
    from app.domains.devices.gateway.device_auth import verify_request_signature

    assert verify_request_signature(secret, payload, sig)


def test_hash_device_secret_roundtrip():
    secret = generate_device_secret()
    hashed = hash_device_secret(secret)
    from app.core.security import verify_password

    assert verify_password(secret, hashed)


def test_push_device_rejects_wrong_mode(db_session):
    device = make_device(name="pull-only", connectivity_mode="pull")
    secret = generate_device_secret()
    device.device_secret_hash = hash_device_secret(secret)
    db_session.add(device)
    db_session.commit()

    auth = DeviceAuthService()
    body = b"{}"
    ts = str(int(time.time()))
    nonce = "abc123"
    payload = build_signature_payload(device_id="pull-only", timestamp=ts, nonce=nonce, body=body)
    sig = sign_request(secret, payload)

    result, error = auth.authenticate_push_request(
        db_session,
        device_id="pull-only",
        timestamp=ts,
        nonce=nonce,
        signature=sig,
        body=body,
        device_secret=secret,
    )
    assert result is None
    assert "push" in (error or "").lower()
