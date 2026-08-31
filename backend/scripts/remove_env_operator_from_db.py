#!/usr/bin/env python3
"""Remove the env-backed operator account row from the users table (one-time migration)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.operator_access import is_env_operator_configured, normalized_operator_email
from app.domains.auth.models.user import User


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete the GOD-mode operator row from users (env credentials must be configured)."
    )
    parser.add_argument(
        "--email",
        help="Operator email to remove (default: AUTH_OPERATOR_EMAIL from env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without applying changes",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the user row",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even when AUTH_OPERATOR_* env vars are not set",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply.", file=sys.stderr)
        return 1

    settings = get_settings()
    email = (args.email or normalized_operator_email() or "").strip().lower()
    if not email:
        print("No operator email provided and AUTH_OPERATOR_EMAIL is not set.", file=sys.stderr)
        return 1

    if not is_env_operator_configured() and not args.force:
        print(
            "AUTH_OPERATOR_EMAIL and AUTH_OPERATOR_PASSWORD must be configured before removing the DB row.",
            file=sys.stderr,
        )
        print("Use --force to override (not recommended).", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            print(f"No users row found for {email}. Nothing to do.")
            return 0

        print(f"Found users.id={user.id} user_uuid={user.user_uuid} email={user.email} role={user.role}")
        if settings.auth_operator_uuid and user.user_uuid != settings.auth_operator_uuid.strip():
            print(
                f"Note: row user_uuid differs from AUTH_OPERATOR_UUID ({settings.auth_operator_uuid}). "
                "Set AUTH_OPERATOR_UUID to the row UUID before --apply to preserve audit correlation."
            )

        if args.dry_run:
            print("Dry run — no changes applied.")
            return 0

        db.execute(delete(User).where(User.id == user.id))
        db.commit()
        print(f"Deleted users row for {email}. Operator login now uses env credentials only.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
