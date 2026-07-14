"""Unit tests for device exception types."""

from __future__ import annotations

import pytest

from app.shared.device_exceptions import (
    AttlogCorrectionError,
    AttlogCorrectionNotSupported,
    DeviceFetchError,
    DeviceLockContentionError,
)


@pytest.mark.testid("BE-UNIT-EXC-001")
def test_device_exception_classes_are_exceptions() -> None:
    classes = (
        DeviceFetchError,
        DeviceLockContentionError,
        AttlogCorrectionNotSupported,
        AttlogCorrectionError,
    )
    for cls in classes:
        assert issubclass(cls, Exception)
        err = cls("boom")
        assert isinstance(err, Exception)
        assert str(err) == "boom"
