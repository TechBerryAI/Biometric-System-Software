"""Low-level ZKTeco attendance log correction via pyzk connection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services.device_attlog_codec import (
    AttlogCapabilities,
    AttlogRecord,
    attendance_to_attlog,
    encode_attlog_blob,
)
from app.services.device_exceptions import AttlogCorrectionError, AttlogCorrectionNotSupported

logger = logging.getLogger(__name__)

_TS_TOLERANCE = timedelta(seconds=2)


def _device_local_naive(dt: datetime, tz_name: str) -> datetime:
    """Normalize DB UTC-aware timestamps to device-local naive time for pyzk."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


def _ts_match(a: datetime, b: datetime, *, tz_name: str) -> bool:
    a_local = _device_local_naive(a, tz_name)
    b_local = _device_local_naive(b, tz_name)
    return abs((a_local - b_local).total_seconds()) <= _TS_TOLERANCE.total_seconds()


def probe_attlog_capabilities(conn: Any) -> AttlogCapabilities:
    """Detect whether selective delete or full rewrite is viable."""
    if hasattr(conn, "delete_attendance") and (
        hasattr(conn, "set_attendance") or hasattr(conn, "save_attendance")
    ):
        record_size = int(getattr(conn, "record_size", 40) or 40)
        return AttlogCapabilities(
            tier="A",
            record_size=record_size,
            supports_selective_delete=True,
            supports_full_rewrite=True,
            supports_write=True,
        )
    try:
        conn.read_sizes()
        record_size = 40
        if getattr(conn, "records", 0) > 0:
            # Infer from device; pyzk stores rec count after read_sizes.
            record_size = 40 if getattr(conn, "user_packet_size", 28) != 28 else 8
        if hasattr(conn, "clear_attendance") and hasattr(conn, "_send_with_buffer"):
            # pyzk exposes clear_attendance + _send_with_buffer but does not commit attlog
            # uploads on real ZKTeco firmware; full rewrite would wipe device memory without
            # restoring punches. Treat as read-only until a verified write path exists.
            return AttlogCapabilities(
                tier="B",
                record_size=record_size,
                supports_selective_delete=False,
                supports_full_rewrite=False,
                supports_write=False,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("attlog capability probe failed: %s", exc)
    return AttlogCapabilities(
        tier="C",
        record_size=40,
        supports_selective_delete=False,
        supports_full_rewrite=False,
        supports_write=False,
    )


def _fetch_attlog_records(conn: Any) -> list[AttlogRecord]:
    raw = conn.get_attendance()
    users = {u.user_id: u.uid for u in conn.get_users()} if hasattr(conn, "get_users") else {}
    out: list[AttlogRecord] = []
    for row in raw:
        uid = int(getattr(row, "uid", 0) or users.get(str(getattr(row, "user_id", "")), 0) or 0)
        out.append(attendance_to_attlog(row, uid=uid))
    return out


def _upload_attlog_records(conn: Any, records: list[AttlogRecord], *, record_size: int) -> None:
    if not hasattr(conn, "_send_with_buffer"):
        raise AttlogCorrectionNotSupported("Device connection does not support attlog upload.")
    blob = encode_attlog_blob(records, record_size=record_size)
    conn._send_with_buffer(blob)
    if hasattr(conn, "refresh_data"):
        conn.refresh_data()


def apply_attlog_correction(
    conn: Any,
    *,
    user_id: str,
    delete_timestamps: list[datetime],
    new_records: list[AttlogRecord],
    tz_name: str = "Asia/Kolkata",
) -> dict[str, Any]:
    """
    Replace attendance punches for one user on the device.

    Tier A: selective delete via conn.delete_attendance when available.
    Tier B: full attlog rewrite (read all → modify → clear → upload all).
    Tier C: raises AttlogCorrectionNotSupported.
    """
    caps = probe_attlog_capabilities(conn)
    if caps.tier == "C":
        raise AttlogCorrectionNotSupported(
            "Device firmware does not support attendance correction. "
            "Selective attlog edit requires Tier A/B firmware capabilities."
        )

    user_id = user_id.strip()
    if not user_id:
        raise AttlogCorrectionError("user_id is required for attlog correction.")

    delete_timestamps = [_device_local_naive(ts, tz_name) for ts in delete_timestamps]
    new_records = [
        AttlogRecord(
            uid=nr.uid,
            user_id=nr.user_id,
            timestamp=_device_local_naive(nr.timestamp, tz_name),
            status=nr.status,
            punch=nr.punch,
        )
        for nr in new_records
    ]

    if hasattr(conn, "disable_device"):
        conn.disable_device()

    try:
        existing = _fetch_attlog_records(conn)
        uid_for_user = next((r.uid for r in existing if r.user_id == user_id), 0)
        if uid_for_user == 0 and new_records:
            uid_for_user = new_records[0].uid

        def _should_delete(rec: AttlogRecord) -> bool:
            if rec.user_id != user_id:
                return False
            return any(_ts_match(rec.timestamp, ts, tz_name=tz_name) for ts in delete_timestamps)

        updated = [r for r in existing if not _should_delete(r)]
        for nr in new_records:
            updated.append(
                AttlogRecord(
                    uid=nr.uid or uid_for_user,
                    user_id=user_id,
                    timestamp=nr.timestamp,
                    status=nr.status,
                    punch=nr.punch,
                )
            )
        updated.sort(key=lambda r: r.timestamp)

        if caps.supports_selective_delete and hasattr(conn, "delete_attendance"):
            for ts in delete_timestamps:
                try:
                    conn.delete_attendance(uid_for_user, ts)
                except TypeError:
                    conn.delete_attendance(user_id=user_id, timestamp=ts)
            for nr in new_records:
                if hasattr(conn, "set_attendance"):
                    conn.set_attendance(
                        uid=nr.uid or uid_for_user,
                        user_id=user_id,
                        timestamp=nr.timestamp,
                        status=nr.status,
                        punch=nr.punch,
                    )
                elif hasattr(conn, "save_attendance"):
                    conn.save_attendance(
                        uid=nr.uid or uid_for_user,
                        user_id=user_id,
                        timestamp=nr.timestamp,
                        status=nr.status,
                        punch=nr.punch,
                    )
        elif caps.supports_full_rewrite:
            conn.clear_attendance()
            if updated:
                _upload_attlog_records(conn, updated, record_size=caps.record_size)
        else:
            raise AttlogCorrectionNotSupported("No viable attlog correction strategy for this device.")

        if hasattr(conn, "refresh_data"):
            conn.refresh_data()

        verify = _fetch_attlog_records(conn)
        for ts in delete_timestamps:
            if any(r.user_id == user_id and _ts_match(r.timestamp, ts, tz_name=tz_name) for r in verify):
                raise AttlogCorrectionError(f"Deleted punch still present on device at {ts.isoformat()}")
        for nr in new_records:
            if not any(
                r.user_id == user_id and _ts_match(r.timestamp, nr.timestamp, tz_name=tz_name)
                for r in verify
            ):
                raise AttlogCorrectionError(f"New punch missing on device readback at {nr.timestamp.isoformat()}")

        return {
            "tier": caps.tier,
            "records_on_device": len(verify),
            "deleted_count": len(delete_timestamps),
            "inserted_count": len(new_records),
        }
    finally:
        if hasattr(conn, "enable_device"):
            conn.enable_device()
