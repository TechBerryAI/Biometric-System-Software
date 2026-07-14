#!/usr/bin/env python3
"""Bulk offboard employees not on the organization roster."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.shared.keep_list import ORGANIZATION_ROSTER  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.domains.employees.services.employee_offboard_service import (  # noqa: E402
    OffboardBulkReport,
    device_write_blockers,
    offboard_all_except_keep_list,
    offboard_device_remnants_only,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _print_section(title: str, rows: list[dict[str, object]], *, empty_msg: str) -> None:
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print(f"  {empty_msg}")
        return
    for row in rows:
        extra = ""
        if "roster_code" in row:
            extra = (
                f" -> roster {row.get('roster_code')} ({row.get('roster_name')})"
                f" [{row.get('match_kind')}]"
            )
        elif "roster_name" in row:
            extra = f" ({row.get('roster_name')})"
        print(
            f"  - id={row.get('id', '—')} "
            f"code={row.get('device_user_id', row.get('roster_code', '—'))} "
            f"name={row.get('name', row.get('roster_name', '—'))}"
            f"{extra}"
        )


def _print_report(report: OffboardBulkReport) -> None:
    _print_section("Will offboard", report.will_offboard, empty_msg="No active employees to offboard.")
    _print_section(
        "Kept (matched roster by code or name)",
        report.kept_by_roster,
        empty_msg="No roster matches among active employees.",
    )
    _print_section(
        "Roster entries missing from DB/device",
        report.keep_list_missing,
        empty_msg="Every roster person is represented in the database.",
    )
    _print_section("Already departed (skipped)", report.already_departed, empty_msg="None.")
    _print_section(
        "Device-only removals",
        report.device_only_removals,
        empty_msg="No extra users on device outside roster.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Offboard employees not on the organization roster.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Default is dry-run only.",
    )
    parser.add_argument(
        "--device-only",
        action="store_true",
        help="Only remove non-roster users from the biometric device (skip DB offboarding).",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    db = SessionLocal()
    try:
        blockers = device_write_blockers(db, device_id=get_settings().zk_device_id)
        if blockers and not dry_run and not args.device_only:
            print("WARNING: Device writes may be blocked:")
            for item in blockers:
                print(f"  - {item}")
            print(
                "\nTo unblock, set the device back to NORMAL mode, for example:\n"
                "  python scripts/restore_device_normal_mode.py\n"
            )

        if dry_run:
            print("DRY RUN — no changes will be made. Pass --execute to apply.")
        elif args.device_only:
            print("EXECUTING device-only cleanup — removes non-roster users from the terminal.")
        else:
            print("EXECUTING offboarding — DB soft-delete + device user removal.")

        if args.device_only:
            report = offboard_device_remnants_only(
                db,
                roster=ORGANIZATION_ROSTER,
                dry_run=dry_run,
            )
        else:
            report = offboard_all_except_keep_list(
                db,
                roster=ORGANIZATION_ROSTER,
                reason="bulk_purge_script",
                dry_run=dry_run,
            )
        _print_report(report)

        if dry_run:
            print(
                f"\nSummary: {len(report.will_offboard)} to offboard, "
                f"{len(report.kept_by_roster)} kept, "
                f"{len(report.keep_list_missing)} roster missing, "
                f"{len(report.device_only_removals)} device-only."
            )
            if blockers:
                print("\nDevice write blockers (fix before --execute):")
                for item in blockers:
                    print(f"  - {item}")
        elif args.device_only:
            print(
                f"\nDone: {report.device_deleted_verified} verified removed from device, "
                f"{report.device_delete_failed} failed, "
                f"{len(report.device_only_removals)} still on device."
            )
        else:
            print(
                f"\nDone: offboarded {len(report.will_offboard)} employees, "
                f"removed {len(report.device_only_removals)} device-only users."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
