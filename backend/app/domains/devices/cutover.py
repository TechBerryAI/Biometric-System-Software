"""Replacement-device cutover gates.

The retired terminal is identified by serial JJA1240500503, not by IP.
A replacement may keep LAN address 192.168.1.119. Inspect is always allowed
so the live serial can be discovered; writes require a different serial.
"""

from __future__ import annotations

from app.domains.devices.models.device import Device

RETIRED_PRIMARY_IP = "192.168.1.119"
RETIRED_PRIMARY_SERIAL = "JJA1240500503"

MIGRATION_FORBIDDEN_COMMANDS = frozenset(
    {
        "DELETE_USER",
        "REMOTE_DELETE",
        "CORRECT_ATTENDANCE",
        "RESTART",
        "FORCE_SYNC",
        "clear_attendance",
        "clear_data",
        "delete_user",
        "delete_attendance",
        "restart",
        "poweroff",
    }
)


class ReplacementHardwareError(ValueError):
    """Live serial still matches the retired terminal, or serial is unconfirmed."""


def replacement_hardware_ready(
    device: Device,
    *,
    serial: str | None = None,
    require_serial: bool = True,
) -> tuple[bool, str | None]:
    ser = serial if serial is not None else device.serial_number
    ser = str(ser or "").strip()
    if not ser:
        if require_serial:
            return False, "Device serial is unknown; inspect the replacement terminal first."
        return True, None
    if ser == RETIRED_PRIMARY_SERIAL:
        return False, (
            f"Device serial still matches retired terminal {RETIRED_PRIMARY_SERIAL}. "
            "The broken unit is still the target."
        )
    return True, None


def assert_replacement_hardware(
    device: Device,
    *,
    serial: str | None = None,
    require_serial: bool = True,
) -> None:
    live = serial if serial is not None else device.serial_number
    ok, reason = replacement_hardware_ready(device, serial=live, require_serial=require_serial)
    if not ok:
        raise ReplacementHardwareError(reason or "Replacement hardware is not confirmed.")


def inspect_snapshot_serial(snapshot: dict | None) -> str | None:
    if not snapshot:
        return None
    raw = snapshot.get("serial_number")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
