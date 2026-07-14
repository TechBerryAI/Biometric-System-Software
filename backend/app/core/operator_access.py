"""Internal operator access checks (database account_flags only)."""

from __future__ import annotations

from typing import Protocol

from app.domains.auth.schemas import UserCapabilities

ACCOUNT_FLAG_EXTENDED = 1


class _OperatorUser(Protocol):
    role: str | None
    account_flags: int


def is_operator_account(user: _OperatorUser | None) -> bool:
    if user is None:
        return False
    flags = int(getattr(user, "account_flags", 0) or 0)
    return user.role == "SUPER_ADMIN" and (flags & ACCOUNT_FLAG_EXTENDED) != 0


def user_capabilities(user: _OperatorUser | None) -> UserCapabilities:
    operator = is_operator_account(user)
    return UserCapabilities(
        attendance_adjust=operator,
        forensic_audit=operator,
    )
