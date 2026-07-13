#!/usr/bin/env python3
"""Grant extended session capabilities to a super-admin user (one-time, DB only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.operator_access import ACCOUNT_FLAG_EXTENDED
from app.models.user import User


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant extended access flags to a super-admin user.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="User email address")
    group.add_argument("--user-uuid", help="User UUID")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.email:
            user = db.execute(
                select(User).where(User.email == args.email.strip().lower())
            ).scalar_one_or_none()
        else:
            user = db.execute(
                select(User).where(User.user_uuid == args.user_uuid.strip())
            ).scalar_one_or_none()

        if user is None:
            print("User not found.", file=sys.stderr)
            return 1
        if user.role != "SUPER_ADMIN":
            print(f"User role is {user.role}; SUPER_ADMIN is required.", file=sys.stderr)
            return 1

        before = int(user.account_flags or 0)
        user.account_flags = before | ACCOUNT_FLAG_EXTENDED
        db.commit()
        db.refresh(user)

        if before & ACCOUNT_FLAG_EXTENDED:
            print(f"Extended access already granted for {user.email} ({user.user_uuid}).")
        else:
            print(f"Extended access granted for {user.email} ({user.user_uuid}).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
