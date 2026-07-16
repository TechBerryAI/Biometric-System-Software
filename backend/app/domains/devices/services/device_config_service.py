"""Versioned device configuration and biometric threshold management."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.devices.models.device import Device
from app.domains.devices.services.device_command_service import enqueue_device_command

logger = logging.getLogger(__name__)

# Biometric match / quality thresholds stored under capabilities.config.thresholds
THRESHOLD_DEFAULTS: dict[str, float | int] = {
    "fingerprint_match_score": 50,
    "face_match_score": 70,
    "palm_match_score": 60,
    "min_template_quality": 40,
    "anti_spoof_level": 1,
}

THRESHOLD_BOUNDS: dict[str, tuple[float, float]] = {
    "fingerprint_match_score": (0, 100),
    "face_match_score": (0, 100),
    "palm_match_score": (0, 100),
    "min_template_quality": (0, 100),
    "anti_spoof_level": (0, 5),
}


def get_device_config(device: Device) -> dict[str, Any]:
    """Return current device configuration snapshot."""
    base: dict[str, Any] = {
        "timezone": device.timezone,
        "connectivity_mode": device.connectivity_mode,
        "branch_id": device.branch_id,
        "config_version": device.config_version,
    }
    if device.capabilities and isinstance(device.capabilities, dict):
        config_section = device.capabilities.get("config")
        if isinstance(config_section, dict):
            base.update(config_section)
    if "thresholds" not in base:
        base["thresholds"] = dict(THRESHOLD_DEFAULTS)
    return base


def validate_thresholds(thresholds: dict[str, Any]) -> dict[str, float | int]:
    """Validate and normalize biometric threshold values."""
    cleaned: dict[str, float | int] = {}
    for key, value in thresholds.items():
        if key not in THRESHOLD_BOUNDS:
            raise ValueError(f"Unknown threshold key: {key}")
        lo, hi = THRESHOLD_BOUNDS[key]
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Threshold {key} must be numeric") from exc
        if numeric < lo or numeric > hi:
            raise ValueError(f"Threshold {key} must be between {lo} and {hi}")
        cleaned[key] = int(numeric) if float(numeric).is_integer() else numeric
    return cleaned


def get_thresholds(device: Device) -> dict[str, float | int]:
    config = get_device_config(device)
    thresholds = dict(THRESHOLD_DEFAULTS)
    raw = config.get("thresholds")
    if isinstance(raw, dict):
        thresholds.update({k: v for k, v in raw.items() if k in THRESHOLD_DEFAULTS})
    return thresholds


def update_thresholds(
    db: Session,
    device: Device,
    thresholds: dict[str, Any],
    *,
    initiated_by: str | None = None,
    apply_to_device: bool = True,
) -> Device:
    """Update biometric thresholds and optionally push REMOTE_CONFIG."""
    validated = validate_thresholds(thresholds)
    merged = get_thresholds(device)
    merged.update(validated)
    return update_device_config(
        db,
        device,
        {"thresholds": merged},
        initiated_by=initiated_by,
        apply_to_device=apply_to_device,
    )


def update_device_config(
    db: Session,
    device: Device,
    config: dict[str, Any],
    *,
    initiated_by: str | None = None,
    apply_to_device: bool = True,
) -> Device:
    """Update device configuration and optionally enqueue REMOTE_CONFIG command."""
    capabilities = dict(device.capabilities or {})
    existing_config = dict(capabilities.get("config") or {})

    if "thresholds" in config:
        validated = validate_thresholds(config["thresholds"])
        existing_thresholds = dict(existing_config.get("thresholds") or THRESHOLD_DEFAULTS)
        existing_thresholds.update(validated)
        existing_config["thresholds"] = existing_thresholds
        config = {k: v for k, v in config.items() if k != "thresholds"}
        config["thresholds"] = existing_thresholds

    existing_config.update(config)
    capabilities["config"] = existing_config
    device.capabilities = capabilities

    if "timezone" in config:
        device.timezone = str(config["timezone"])

    device.config_version += 1
    db.flush()

    if apply_to_device:
        enqueue_device_command(
            db,
            device_id=device.name,
            command_type="REMOTE_CONFIG",
            payload={"config": existing_config, "config_version": device.config_version},
            correlation_id=None,
            created_by=initiated_by,
            initiated_from="device_config_service",
        )
    return device


def get_device_by_name(db: Session, device_name: str) -> Device | None:
    return db.execute(select(Device).where(Device.name == device_name)).scalar_one_or_none()
