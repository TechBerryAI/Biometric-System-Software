"""Structured AI telemetry logging helpers."""

from __future__ import annotations

import logging
from typing import Any

SENSITIVE_KEYS = {"api_key", "authorization", "xai_api_key", "token"}


def log_ai_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    safe_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower() in SENSITIVE_KEYS:
            safe_fields[key] = "***redacted***"
        else:
            safe_fields[key] = value
    kv = " ".join(f"{k}={safe_fields[k]}" for k in sorted(safe_fields.keys()))
    logger.info("ai.event=%s %s", event, kv)

