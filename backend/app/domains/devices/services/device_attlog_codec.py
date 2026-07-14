"""Encode/decode ZKTeco attendance log records for device read/write."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from struct import pack, unpack


@dataclass(frozen=True, slots=True)
class AttlogCapabilities:
    tier: str  # A | B | C
    record_size: int
    supports_selective_delete: bool
    supports_full_rewrite: bool
    supports_write: bool


@dataclass(frozen=True, slots=True)
class AttlogRecord:
    uid: int
    user_id: str
    timestamp: datetime
    status: int
    punch: int


def encode_time_zk(t: datetime) -> bytes:
    """ZK time encoding (matches pyzk __encode_time)."""
    d = (
        ((t.year % 100) * 12 * 31 + ((t.month - 1) * 31) + t.day - 1) * (24 * 60 * 60)
        + (t.hour * 60 + t.minute) * 60
        + t.second
    )
    return pack("<I", int(d))


def decode_time_zk(raw: bytes) -> datetime:
    d = unpack("I", raw.ljust(4, b"\x00")[:4])[0]
    second = d % 60
    d //= 60
    minute = d % 60
    d //= 60
    hour = d % 24
    d //= 24
    day = d % 31 + 1
    d //= 31
    month = d % 12 + 1
    year = (d // 12) + 2000
    return datetime(year, month, day, hour, minute, second)


def encode_attlog_record_40(*, uid: int, user_id: str, timestamp: datetime, status: int, punch: int) -> bytes:
    user_id_bytes = user_id.encode("utf-8", errors="ignore")[:24].ljust(24, b"\x00")
    return pack(
        "<H24sB4sB8s",
        int(uid),
        user_id_bytes,
        int(status),
        encode_time_zk(timestamp),
        int(punch),
        b"\x00" * 8,
    )


def encode_attlog_record_8(*, uid: int, timestamp: datetime, status: int, punch: int) -> bytes:
    return pack("HB4sB", int(uid), int(status), encode_time_zk(timestamp), int(punch))


def encode_attlog_record_16(*, user_id: str, timestamp: datetime, status: int, punch: int) -> bytes:
    uid = int(user_id) if str(user_id).isdigit() else 0
    return pack("<I4sBB2sI", uid, encode_time_zk(timestamp), int(status), int(punch), b"\x00\x00", 0)


def encode_attlog_blob(records: list[AttlogRecord], *, record_size: int) -> bytes:
    chunks: list[bytes] = []
    for rec in records:
        if record_size == 8:
            chunks.append(
                encode_attlog_record_8(
                    uid=rec.uid,
                    timestamp=rec.timestamp,
                    status=rec.status,
                    punch=rec.punch,
                )
            )
        elif record_size == 16:
            chunks.append(
                encode_attlog_record_16(
                    user_id=rec.user_id,
                    timestamp=rec.timestamp,
                    status=rec.status,
                    punch=rec.punch,
                )
            )
        else:
            chunks.append(
                encode_attlog_record_40(
                    uid=rec.uid,
                    user_id=rec.user_id,
                    timestamp=rec.timestamp,
                    status=rec.status,
                    punch=rec.punch,
                )
            )
    body = b"".join(chunks)
    return pack("<I", len(body)) + body


def attendance_to_attlog(record: object, *, uid: int) -> AttlogRecord:
    user_id = str(getattr(record, "user_id", "") or "")
    ts = getattr(record, "timestamp", None)
    if not isinstance(ts, datetime):
        raise ValueError("attendance record missing timestamp")
    return AttlogRecord(
        uid=int(getattr(record, "uid", uid) or uid),
        user_id=user_id,
        timestamp=ts,
        status=int(getattr(record, "status", 0) or 0),
        punch=int(getattr(record, "punch", 0) or 0),
    )
