"""Lightweight pyzk simulator for reliability-focused tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from random import random
from zoneinfo import ZoneInfo


@dataclass
class SimulatedUser:
    user_id: str
    name: str
    uid: int
    privilege: int = 0
    group_id: str = ""
    card: str = ""


class SimulatedPyZKDevice:
    """Fault-injectable simulator for firmware tolerance tests."""

    def __init__(self, *, firmware_version: str = "sim-fw-1", fail_rate: float = 0.0) -> None:
        self.firmware_version = firmware_version
        self.fail_rate = fail_rate
        self.users: dict[str, SimulatedUser] = {}
        self.attendance: list[tuple[str, datetime]] = []

    def _should_fail(self) -> bool:
        return self.fail_rate > 0 and random() < self.fail_rate

    def get_users(self) -> list[SimulatedUser]:
        if self._should_fail():
            raise TimeoutError("simulated get_users timeout")
        return list(self.users.values())

    def set_user(self, *, user_id: str, name: str, uid: int, privilege: int = 0, group_id: str = "", card: int = 0) -> None:
        if self._should_fail():
            raise OSError("simulated write failure")
        self.users[user_id] = SimulatedUser(
            user_id=user_id,
            name=name,
            uid=uid,
            privilege=privilege,
            group_id=group_id,
            card=str(card),
        )

    def add_attendance(self, user_id: str) -> None:
        self.attendance.append((user_id, datetime.now(ZoneInfo("UTC"))))
