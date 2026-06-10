"""Probe ZKTeco device attlog correction capabilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.device_service import DeviceService  # noqa: E402


def main() -> None:
    service = DeviceService()
    fingerprint = service.detect_firmware_fingerprint()
    caps = service.probe_attlog_capabilities()
    print(json.dumps({"firmware": fingerprint, "attlog_capabilities": caps}, indent=2))


if __name__ == "__main__":
    main()
