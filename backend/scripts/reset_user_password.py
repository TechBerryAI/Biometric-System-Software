#!/usr/bin/env python3
"""Reset a login user's password (bcrypt hash + revoke sessions)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.operator_access import is_env_operator_email
from app.core.security import hash_password
from app.domains.auth.models.user import User
from app.domains.auth.services.auth_service import revoke_all_user_refresh_tokens


def main() -> int:
    parser = argparse.ArgumentParser(description="Set a users.password_hash and sign out existing sessions.")
    parser.add_argument("--email", required=True, help="Login email stored in the users table")
    parser.add_argument("--password", required=True, help="New plaintext password (hashed before write)")
    parser.add_argument("--dry-run", action="store_true", help="Show the matching user without applying changes")
    parser.add_argument("--apply", action="store_true", help="Write the new password hash")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply.", file=sys.stderr)
        return 1

    email = args.email.strip().lower()
    if is_env_operator_email(email):
        print(
            "This email is the env-backed operator. Change AUTH_OPERATOR_PASSWORD instead.",
            file=sys.stderr,
        )
        return 1

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            print(f"No users row found for {email}.", file=sys.stderr)
            return 1
        if not user.active:
            print(f"User {email} is inactive.", file=sys.stderr)
            return 1

        print(f"Found users.id={user.id} user_uuid={user.user_uuid} email={user.email} role={user.role}")
        if args.dry_run:
            print("Dry run — no changes applied.")
            return 0

        user.password_hash = hash_password(args.password)
        revoked = revoke_all_user_refresh_tokens(db, user.id)
        db.commit()
        print(f"Password updated for {email}. Revoked {revoked} active session(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
