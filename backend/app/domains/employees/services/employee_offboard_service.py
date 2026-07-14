"""Employee offboarding: soft-delete in DB and remove from biometric device."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.keep_list import (
    ORGANIZATION_ROSTER,
    match_employee_to_roster,
)
from app.core import device_policy
from app.core.config import Settings, get_settings
from app.domains.devices.models.device import Device
from app.domains.employees.models.device_user_mapping import DeviceUserMapping
from app.domains.employees.models.employee import Employee
from app.domains.devices.services.device_command_service import enqueue_device_command, process_command
from app.domains.devices.services.device_service import DeviceService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _deactivate_device_mappings(
    db: Session,
    *,
    employee_uuid: str,
    device_id: str,
    effective_at: datetime,
) -> None:
    rows = db.execute(
        select(DeviceUserMapping).where(
            DeviceUserMapping.employee_uuid == employee_uuid,
            DeviceUserMapping.device_id == device_id,
            DeviceUserMapping.active.is_(True),
        )
    ).scalars().all()
    for row in rows:
        row.active = False
        row.valid_to = effective_at


def _resolve_device_uid(
    employee: Employee,
    *,
    device_service: DeviceService | None = None,
) -> int | None:
    if employee.device_uid is not None and employee.device_uid > 0:
        return int(employee.device_uid)
    if device_service is None:
        return None
    return device_service.resolve_uid_for_user_id(employee.device_user_id)


def enqueue_delete_user_command(
    db: Session,
    *,
    device_id: str,
    user_id: str,
    uid: int | None,
    correlation_id: str | None = None,
    created_by: str | None = None,
    initiated_from: str = "offboard",
    process_inline: bool = True,
    settings: Settings | None = None,
) -> None:
    """Queue (and optionally run) device user deletion."""
    cfg = settings or get_settings()
    payload: dict[str, object] = {"user_id": user_id.strip()}
    if uid is not None and uid > 0:
        payload["uid"] = int(uid)
    command = enqueue_device_command(
        db,
        device_id=device_id,
        command_type="DELETE_USER",
        payload=payload,
        correlation_id=correlation_id,
        created_by=created_by,
        initiated_from=initiated_from,
    )
    if process_inline:
        process_command(db, command, settings=cfg, worker_id="api-inline")


def offboard_employee(
    db: Session,
    employee: Employee,
    *,
    actor_user_uuid: str | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    process_device_inline: bool = True,
    settings: Settings | None = None,
) -> bool:
    """
    Soft-offboard an employee: mark departed, deactivate mappings, remove from device.

    Returns True if offboarding was applied; False if already departed.
    """
    cfg = settings or get_settings()
    now = _utcnow()
    if employee.departed_at is not None:
        return False

    employee.departed_at = now
    if not employee.employee_uuid:
        from uuid import uuid4

        employee.employee_uuid = str(uuid4())
        db.flush()

    _deactivate_device_mappings(
        db,
        employee_uuid=employee.employee_uuid,
        device_id=cfg.zk_device_id,
        effective_at=now,
    )

    uid: int | None = None
    try:
        device_service = DeviceService(settings=cfg)
        uid = _resolve_device_uid(employee, device_service=device_service)
    except Exception:  # noqa: BLE001
        uid = _resolve_device_uid(employee)

    try:
        enqueue_delete_user_command(
            db,
            device_id=cfg.zk_device_id,
            user_id=employee.device_user_id,
            uid=uid,
            correlation_id=request_id,
            created_by=actor_user_uuid,
            initiated_from="offboard:employee",
            process_inline=process_device_inline,
            settings=cfg,
        )
    except RuntimeError:
        # Governance/read-only may block device writes; DB offboard still applies.
        pass

    db.flush()
    return True


def offboard_device_user_only(
    db: Session,
    *,
    user_id: str,
    uid: int | None = None,
    actor_user_uuid: str | None = None,
    request_id: str | None = None,
    process_device_inline: bool = True,
    settings: Settings | None = None,
) -> None:
    """Remove a device user with no matching employee row."""
    cfg = settings or get_settings()
    resolved_uid = uid
    if resolved_uid is None or resolved_uid <= 0:
        device_service = DeviceService(settings=cfg)
        resolved_uid = device_service.resolve_uid_for_user_id(user_id)
    try:
        enqueue_delete_user_command(
            db,
            device_id=cfg.zk_device_id,
            user_id=user_id,
            uid=resolved_uid,
            correlation_id=request_id,
            created_by=actor_user_uuid,
            initiated_from="offboard:device_only",
            process_inline=process_device_inline,
            settings=cfg,
        )
    except RuntimeError:
        pass


def restore_device_writable_state(db: Session, *, device_id: str | None = None) -> str:
    """
    Clear QUARANTINED/DEGRADED mode so maintenance deletes can run.
    Returns previous device mode.
    """
    cfg = get_settings()
    target = device_id or cfg.zk_device_id
    device = db.execute(select(Device).where(Device.name == target)).scalar_one_or_none()
    if device is None:
        raise RuntimeError(f"Device '{target}' not found in registry.")
    previous_mode = device.mode
    device.mode = "NORMAL"
    device.quarantine_reason = None
    db.flush()
    return previous_mode


def delete_device_user_verified(
    *,
    user_id: str,
    uid: int | None = None,
    settings: Settings | None = None,
) -> bool:
    """Delete one user from the terminal and verify removal (bypasses command queue)."""
    from app.domains.devices.services.device_command_service import device_session_lock

    cfg = settings or get_settings()
    service = DeviceService(settings=cfg)
    normalized_id = user_id.strip()
    with device_session_lock(cfg.zk_device_id, cfg):
        already_gone, _ = service.verify_user_deleted(user_id=normalized_id)
        if already_gone:
            return True
        resolved_uid = int(uid) if uid is not None and uid > 0 else service.resolve_uid_for_user_id(normalized_id)
        service.delete_user(uid=resolved_uid, user_id=normalized_id)
        ok, _ = service.verify_user_deleted(user_id=normalized_id)
        return ok


@dataclass(slots=True)
class OffboardBulkReport:
    will_offboard: list[dict[str, object]] = field(default_factory=list)
    kept_by_roster: list[dict[str, object]] = field(default_factory=list)
    keep_list_missing: list[dict[str, object]] = field(default_factory=list)
    already_departed: list[dict[str, object]] = field(default_factory=list)
    device_only_removals: list[dict[str, object]] = field(default_factory=list)
    device_deleted_verified: int = 0
    device_delete_failed: int = 0


def _roster_tuple(
    keep_device_user_ids: Sequence[str] | None,
) -> tuple[tuple[str, str], ...]:
    if keep_device_user_ids is None:
        return ORGANIZATION_ROSTER
    # Legacy callers passing only codes — resolve names from full roster when possible.
    roster_by_code = {code: name for code, name in ORGANIZATION_ROSTER}
    out: list[tuple[str, str]] = []
    for code in keep_device_user_ids:
        normalized = str(code).strip()
        if not normalized:
            continue
        out.append((normalized, roster_by_code.get(normalized, normalized)))
    return tuple(out)


def build_offboard_report(
    db: Session,
    keep_device_user_ids: Sequence[str] | None = None,
    *,
    roster: tuple[tuple[str, str], ...] | None = None,
    settings: Settings | None = None,
) -> OffboardBulkReport:
    """Dry-run report for bulk offboarding against organization roster."""
    cfg = settings or get_settings()
    active_roster = roster or _roster_tuple(keep_device_user_ids)
    report = OffboardBulkReport()

    employees = list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())
    matched_roster_codes: set[str] = set()

    for emp in employees:
        roster_match = match_employee_to_roster(
            device_user_id=emp.device_user_id,
            name=emp.name,
            roster=active_roster,
        )
        if roster_match is not None:
            matched_roster_codes.add(roster_match.roster_code)
            if emp.departed_at is None:
                report.kept_by_roster.append(
                    {
                        "id": emp.id,
                        "device_user_id": emp.device_user_id,
                        "name": emp.name,
                        "roster_code": roster_match.roster_code,
                        "roster_name": roster_match.roster_name,
                        "match_kind": roster_match.match_kind,
                    }
                )
            continue

        row = {"id": emp.id, "device_user_id": emp.device_user_id, "name": emp.name}
        if emp.departed_at is not None:
            report.already_departed.append(row)
        else:
            report.will_offboard.append(row)

    for roster_code, roster_name in active_roster:
        if roster_code not in matched_roster_codes:
            report.keep_list_missing.append(
                {"roster_code": roster_code, "roster_name": roster_name}
            )

    try:
        device_service = DeviceService(settings=cfg)
        for user in device_service.fetch_users():
            code = user.user_id.strip()
            if not code:
                continue
            roster_match = match_employee_to_roster(
                device_user_id=code,
                name=user.name,
                roster=active_roster,
            )
            if roster_match is not None:
                continue
            report.device_only_removals.append(
                {"device_user_id": code, "uid": int(user.uid), "name": user.name}
            )
    except Exception:  # noqa: BLE001
        pass

    return report


def offboard_all_except_keep_list(
    db: Session,
    keep_device_user_ids: Sequence[str] | None = None,
    *,
    roster: tuple[tuple[str, str], ...] | None = None,
    actor_user_uuid: str | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    dry_run: bool = True,
    settings: Settings | None = None,
) -> OffboardBulkReport:
    """Offboard every active employee not matched to the organization roster."""
    report = build_offboard_report(
        db,
        keep_device_user_ids,
        roster=roster,
        settings=settings,
    )
    if dry_run:
        return report

    for row in report.will_offboard:
        emp = db.get(Employee, int(row["id"]))
        if emp is None or emp.departed_at is not None:
            continue
        offboard_employee(
            db,
            emp,
            actor_user_uuid=actor_user_uuid,
            reason=reason or "bulk_purge",
            request_id=request_id,
            process_device_inline=True,
            settings=settings,
        )

    for row in report.device_only_removals:
        offboard_device_user_only(
            db,
            user_id=str(row["device_user_id"]),
            uid=int(row["uid"]) if row.get("uid") is not None else None,
            actor_user_uuid=actor_user_uuid,
            request_id=request_id,
            process_device_inline=True,
            settings=settings,
        )

    db.commit()
    return report


def offboard_device_remnants_only(
    db: Session,
    *,
    roster: tuple[tuple[str, str], ...] | None = None,
    actor_user_uuid: str | None = None,
    request_id: str | None = None,
    dry_run: bool = True,
    settings: Settings | None = None,
) -> OffboardBulkReport:
    """Remove non-roster users from the biometric device only (DB unchanged)."""
    report = build_offboard_report(db, roster=roster, settings=settings)
    if dry_run:
        return report

    if not device_policy.DEVICE_WRITES_ENABLED:
        logger.error("Device writes disabled by policy — cannot delete users from terminal.")
        return report

    previous_mode = restore_device_writable_state(db)
    db.commit()
    logger.info("Device mode restored for cleanup (%s -> NORMAL)", previous_mode)

    verified = 0
    failed = 0
    cfg = settings or get_settings()
    for row in list(report.device_only_removals):
        user_id = str(row["device_user_id"])
        uid = int(row["uid"]) if row.get("uid") is not None else None
        try:
            if delete_device_user_verified(user_id=user_id, uid=uid, settings=cfg):
                verified += 1
            else:
                failed += 1
                logger.warning("Device user still present after delete: %s", user_id)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("Device delete failed for %s: %s", user_id, exc)

    report.device_deleted_verified = verified
    report.device_delete_failed = failed
    logger.info("Device-only cleanup: %s verified removed, %s failed", verified, failed)

    # Refresh device-only list after execution.
    after = build_offboard_report(db, roster=roster, settings=settings)
    report.device_only_removals = after.device_only_removals
    return report


def device_write_blockers(db: Session, *, device_id: str | None = None) -> list[str]:
    """Return human-readable reasons device writes may be blocked."""
    cfg = get_settings()
    target = device_id or cfg.zk_device_id
    from app.domains.ops.services.system_governance_service import assert_device_write_allowed

    blockers: list[str] = []
    if not device_policy.DEVICE_WRITES_ENABLED:
        blockers.append("Device writes disabled by internal policy")
    allowed, reason = assert_device_write_allowed(db, device_id=target)
    if not allowed and reason:
        blockers.append(reason)
    return blockers
