"""Device communication and attlog correction errors."""

from __future__ import annotations


class DeviceFetchError(RuntimeError):
    """Raised when attendance or user fetch fails (distinct from empty result)."""


class AttlogCorrectionNotSupported(RuntimeError):
    """Device firmware does not support safe individual attlog correction."""


class AttlogCorrectionError(RuntimeError):
    """Attendance correction on device failed verification or protocol error."""
