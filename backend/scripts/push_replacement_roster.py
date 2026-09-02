#!/usr/bin/env python3
"""One-shot CREATE of active employee metadata onto the replacement terminal."""

from __future__ import annotations

import logging
import sys

import app.models  # noqa: F401

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domains.devices.cutover import RETIRED_PRIMARY_SERIAL
from app.domains.devices.services.device_migration_service import (
    execute_migration,
    inspect_device,
    migration_to_dict,
    run_dry_run,
)
from app.domains.devices.services.device_registry_service import get_device_by_name
from app.shared.ids import new_user_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

TARGET_IP = "192.168.1.119"
TARGET_NAME = "main-entrance"


def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    actor = new_user_id()
    try:
        device = get_device_by_name(db, TARGET_NAME)
        if device is None:
            print(f"{TARGET_NAME} not found", file=sys.stderr)
            return 1
        print(f"target {device.name} ip={device.ip_address} serial={device.serial_number} mode={device.mode}")
        if (device.ip_address or "").strip() != TARGET_IP:
            print(f"refusing unexpected ip {device.ip_address}", file=sys.stderr)
            return 1

        snapshot = inspect_device(db, device, settings=settings)
        db.commit()
        db.refresh(device)
        serial = str(snapshot.get("serial_number") or "").strip()
        print(
            f"inspect serial={serial} users={snapshot.get('user_count')} "
            f"confirmed={snapshot.get('replacement_confirmed')}"
        )
        if serial == RETIRED_PRIMARY_SERIAL or not snapshot.get("replacement_confirmed"):
            print(snapshot.get("replacement_blocker") or "replacement not confirmed", file=sys.stderr)
            return 1

        migration = run_dry_run(db, device, include_departed=False, created_by=actor)
        db.commit()
        db.refresh(migration)
        print("dry-run", migration.migration_uuid, migration.preflight_summary)

        migration = execute_migration(
            db,
            device,
            migration.migration_uuid,
            confirm_target_device_name=TARGET_NAME,
            confirm_target_ip=TARGET_IP,
            approved_by=actor,
            settings=settings,
        )
        db.commit()
        db.refresh(migration)
        payload = migration_to_dict(migration)
        print("RESULT", payload.get("status"), (payload.get("report") or {}).get("totals"))
        failed = [row["device_user_id"] for row in payload.get("items") or [] if row.get("status") == "FAILED"]
        if failed:
            print("failed_user_ids", failed)
            return 2
        print(payload.get("fingerprint_next_step"))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
