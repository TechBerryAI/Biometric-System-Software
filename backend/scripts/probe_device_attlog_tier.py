#!/usr/bin/env python3
"""Probe the configured biometric device for attlog correction tier (A/B/C)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import device_policy
from app.core.config import get_settings
from app.domains.devices.services.device_service import DeviceService


def main() -> int:
    settings = get_settings()
    device = DeviceService(settings=settings)
    try:
        caps = device.probe_attlog_capabilities()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc), "tier": "unknown"}, indent=2))
        return 1

    tier = str(caps.get("tier") or "C")
    payload = {
        "device_id": settings.zk_device_id,
        "device_ip": settings.zk_device_ip,
        "tier": tier,
        "supports_write": bool(caps.get("supports_write")),
        "supports_selective_delete": bool(caps.get("supports_selective_delete")),
        "supports_full_rewrite": bool(caps.get("supports_full_rewrite")),
        "tier_b_rewrite_policy": device_policy.ATTLOG_TIER_B_REWRITE,
        "recommendation": (
            "Tier A: selective attlog write is supported."
            if tier == "A"
            else (
                "Tier B: set ATTLOG_TIER_B_REWRITE in app.core.device_policy after verifying readback."
                if tier == "B"
                else "Tier C: device does not support attlog correction."
            )
        ),
    }
    print(json.dumps(payload, indent=2))
    return 0 if tier in ("A", "B") else 2


if __name__ == "__main__":
    raise SystemExit(main())
