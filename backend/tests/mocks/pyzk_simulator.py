"""Lightweight pyzk simulator for reliability-focused tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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


@dataclass
class SimulatedAttendance:
    user_id: str
    timestamp: datetime
    status: int
    punch: int
    uid: int


class SimulatedPyZKConnection:
    """In-memory device connection with attlog CRUD for correction tests."""

    record_size = 40

    def __init__(self, device: "SimulatedPyZKDevice") -> None:
        self._device = device

    def read_sizes(self) -> None:
        self._device.records = len(self._device.attendance)

    @property
    def records(self) -> int:
        return len(self._device.attendance)

    def get_users(self) -> list[SimulatedUser]:
        return self._device.get_users()

    def get_attendance(self) -> list[SimulatedAttendance]:
        return list(self._device.attendance)

    def clear_attendance(self) -> bool:
        self._device.attendance.clear()
        return True

    def _send_with_buffer(self, _blob: bytes) -> None:
        # Full rewrite path stores decoded records separately in tests via direct API.
        return None

    def refresh_data(self) -> None:
        return None

    def disable_device(self) -> None:
        return None

    def enable_device(self) -> None:
        return None

    def delete_attendance(self, uid: int, timestamp: datetime) -> None:
        self._device.delete_attendance(uid=uid, user_id="", timestamp=timestamp)

    def set_attendance(
        self,
        *,
        uid: int,
        user_id: str,
        timestamp: datetime,
        status: int,
        punch: int,
    ) -> None:
        self._device.write_attendance(
            uid=uid,
            user_id=user_id,
            timestamp=timestamp,
            status=status,
            punch=punch,
        )


@dataclass
class SimulatedPyZKDevice:
    """Fault-injectable simulator for firmware tolerance tests."""

    firmware_version: str = "sim-fw-1"
    fail_rate: float = 0.0
    users: dict[str, SimulatedUser] = field(default_factory=dict)
    attendance: list[SimulatedAttendance] = field(default_factory=list)

    def connection(self) -> SimulatedPyZKConnection:
        return SimulatedPyZKConnection(self)

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

    def add_attendance(self, user_id: str, *, timestamp: datetime | None = None, punch: int = 0, status: int = 0) -> None:
        uid = self.users[user_id].uid if user_id in self.users else 0
        self.attendance.append(
            SimulatedAttendance(
                user_id=user_id,
                timestamp=timestamp or datetime.now(ZoneInfo("UTC")),
                status=status,
                punch=punch,
                uid=uid,
            )
        )

    def delete_attendance(self, *, uid: int, user_id: str, timestamp: datetime) -> None:
        tol = timedelta(seconds=2)
        self.attendance = [
            row
            for row in self.attendance
            if not (
                (row.uid == uid or (user_id and row.user_id == user_id))
                and abs((row.timestamp - timestamp).total_seconds()) <= tol.total_seconds()
            )
        ]

    def write_attendance(
        self,
        *,
        uid: int,
        user_id: str,
        timestamp: datetime,
        status: int,
        punch: int,
    ) -> None:
        self.attendance.append(
            SimulatedAttendance(
                user_id=user_id,
                timestamp=timestamp,
                status=status,
                punch=punch,
                uid=uid,
            )
        )
        self.attendance.sort(key=lambda r: r.timestamp)

    def replace_attendance(self, records: list[SimulatedAttendance]) -> None:
        self.attendance = sorted(records, key=lambda r: r.timestamp)
