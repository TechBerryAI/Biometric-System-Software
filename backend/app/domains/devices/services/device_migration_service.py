"""Replacement-device employee metadata migration (CREATE-only by default)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.domains.devices.cutover import (
    MIGRATION_FORBIDDEN_COMMANDS,
    ReplacementHardwareError,
    assert_replacement_hardware,
    inspect_snapshot_serial,
    replacement_hardware_ready,
)
from app.domains.devices.models.device import Device
from app.domains.devices.models.device_migration import DeviceMigration, DeviceMigrationItem
from app.domains.devices.services.device_command_service import (
    device_session_lock,
    enqueue_device_command,
    process_command,
)
from app.domains.devices.services.device_registry_service import device_service_for
from app.domains.devices.services.device_service import format_device_connection_error
from app.domains.employees.models.employee import Employee
from app.shared.device_exceptions import DeviceLockContentionError

logger = logging.getLogger(__name__)

ALLOWED_EXECUTE_COMMAND = "UPSERT_USER"


def _utcnow() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def _norm_card(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "0"):
        return None
    return text


def _norm_group(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_privilege(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _norm_name(value: Any) -> str:
    return str(value or "").strip()


def metadata_matches(employee: Employee, device_user: dict[str, Any]) -> bool:
    return (
        _norm_name(employee.name) == _norm_name(device_user.get("name"))
        and _norm_privilege(employee.device_privilege) == _norm_privilege(device_user.get("privilege"))
        and _norm_group(employee.device_group_id) == _norm_group(device_user.get("group_id"))
        and _norm_card(employee.device_card) == _norm_card(device_user.get("card"))
    )


def next_free_uid(occupied: set[int], preferred: int | None) -> int:
    if preferred is not None and preferred > 0 and preferred not in occupied:
        return int(preferred)
    candidate = 1
    while candidate in occupied:
        candidate += 1
    return candidate


def last_inspect_snapshot(device: Device) -> dict[str, Any] | None:
    caps = device.capabilities if isinstance(device.capabilities, dict) else None
    if not caps:
        return None
    snap = caps.get("last_inspect")
    return snap if isinstance(snap, dict) else None


def persist_inspect_snapshot(device: Device, snapshot: dict[str, Any]) -> None:
    caps = dict(device.capabilities) if isinstance(device.capabilities, dict) else {}
    stored = {
        key: snapshot.get(key)
        for key in (
            "connected",
            "connection_detail",
            "firmware_version",
            "serial_number",
            "platform",
            "fp_version",
            "face_version",
            "users",
            "user_count",
            "unsupported",
            "errors",
            "inspected_at",
            "replacement_confirmed",
        )
    }
    caps["last_inspect"] = stored
    if snapshot.get("platform"):
        caps["platform"] = snapshot["platform"]
    caps["supports_user_write"] = True
    device.capabilities = caps
    fw = snapshot.get("firmware_version")
    if fw:
        device.firmware_version = str(fw)[:128]
    serial = snapshot.get("serial_number")
    if serial:
        device.serial_number = str(serial)[:128]
    if snapshot.get("connected"):
        device.health_status = "ONLINE"
        device.last_seen = _utcnow()
        if device.mode in {"OFFLINE", "DEGRADED"}:
            device.mode = "NORMAL"


def inspect_device(
    db: Session,
    device: Device,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Read-only DISCOVER. Always allowed so a replacement at the old IP can be identified."""
    settings = settings or get_settings()
    service = device_service_for(db, device_name=device.name, settings=settings)
    try:
        with device_session_lock(device.name, settings, blocking_timeout=90):
            snapshot = service.inspect_readonly()
    except DeviceLockContentionError as exc:
        raise RuntimeError(str(exc)) from exc
    snapshot = dict(snapshot)
    snapshot["inspected_at"] = _utcnow().isoformat()
    serial = inspect_snapshot_serial(snapshot)
    ready, reason = replacement_hardware_ready(device, serial=serial, require_serial=bool(serial))
    if not serial:
        ready, reason = replacement_hardware_ready(device, serial=serial, require_serial=True)
    snapshot["replacement_confirmed"] = bool(ready)
    snapshot["replacement_blocker"] = None if ready else reason
    persist_inspect_snapshot(device, snapshot)
    db.flush()
    return snapshot


def _roster(db: Session, *, include_departed: bool) -> list[Employee]:
    stmt = select(Employee).order_by(Employee.id)
    if not include_departed:
        stmt = stmt.where(Employee.departed_at.is_(None))
    return list(db.execute(stmt).scalars().all())


def _users_by_id(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not snapshot:
        return out
    for row in snapshot.get("users") or []:
        if not isinstance(row, dict):
            continue
        user_id = str(row.get("user_id") or "").strip()
        if user_id:
            out[user_id] = row
    return out


def _occupied_uids(snapshot: dict[str, Any] | None) -> set[int]:
    occupied: set[int] = set()
    if not snapshot:
        return occupied
    for row in snapshot.get("users") or []:
        if not isinstance(row, dict):
            continue
        try:
            uid = int(row.get("uid") or 0)
        except (TypeError, ValueError):
            continue
        if uid > 0:
            occupied.add(uid)
    return occupied


def plan_actions(
    employees: Iterable[Employee],
    snapshot: dict[str, Any] | None,
    *,
    approve_update_user_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    approved = {item.strip() for item in (approve_update_user_ids or set()) if item.strip()}
    by_id = _users_by_id(snapshot)
    occupied = _occupied_uids(snapshot)
    rows: list[dict[str, Any]] = []
    for emp in employees:
        user_id = str(emp.device_user_id or "").strip()
        preferred = int(emp.device_uid) if emp.device_uid and emp.device_uid > 0 else None
        existing = by_id.get(user_id)
        if existing is None:
            planned_uid = next_free_uid(occupied, preferred)
            occupied.add(planned_uid)
            rows.append(
                {
                    "employee_id": emp.id,
                    "employee_uuid": emp.employee_uuid,
                    "device_user_id": user_id,
                    "name": emp.name,
                    "uid": planned_uid,
                    "card": emp.device_card,
                    "privilege": emp.device_privilege,
                    "group_id": emp.device_group_id,
                    "action": "CREATE",
                    "conflict": None,
                }
            )
            continue
        if metadata_matches(emp, existing):
            try:
                existing_uid = int(existing.get("uid") or 0) or preferred
            except (TypeError, ValueError):
                existing_uid = preferred
            rows.append(
                {
                    "employee_id": emp.id,
                    "employee_uuid": emp.employee_uuid,
                    "device_user_id": user_id,
                    "name": emp.name,
                    "uid": existing_uid,
                    "card": emp.device_card,
                    "privilege": emp.device_privilege,
                    "group_id": emp.device_group_id,
                    "action": "SKIP",
                    "conflict": None,
                }
            )
            continue
        if user_id in approved:
            try:
                existing_uid = int(existing.get("uid") or 0) or preferred
            except (TypeError, ValueError):
                existing_uid = preferred
            rows.append(
                {
                    "employee_id": emp.id,
                    "employee_uuid": emp.employee_uuid,
                    "device_user_id": user_id,
                    "name": emp.name,
                    "uid": existing_uid,
                    "card": emp.device_card,
                    "privilege": emp.device_privilege,
                    "group_id": emp.device_group_id,
                    "action": "UPDATE",
                    "conflict": None,
                }
            )
            continue
        rows.append(
            {
                "employee_id": emp.id,
                "employee_uuid": emp.employee_uuid,
                "device_user_id": user_id,
                "name": emp.name,
                "uid": existing.get("uid"),
                "card": emp.device_card,
                "privilege": emp.device_privilege,
                "group_id": emp.device_group_id,
                "action": "CONFLICT",
                "conflict": (
                    f"user_id '{user_id}' already exists on the replacement device "
                    f"with different metadata (device name={existing.get('name')!r})."
                ),
            }
        )
    return rows


def _preflight_summary(employees: list[Employee], planned: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    missing_user_id = sum(1 for e in employees if not str(e.device_user_id or "").strip())
    user_ids = [str(e.device_user_id).strip() for e in employees if str(e.device_user_id or "").strip()]
    duplicate_user_id = len(user_ids) - len(set(user_ids))
    cards = [_norm_card(e.device_card) for e in employees]
    nonempty_cards = [c for c in cards if c]
    duplicate_card = len(nonempty_cards) - len(set(nonempty_cards))
    return {
        "total_employees_in_scope": len(employees),
        "valid_for_migration": sum(1 for row in planned if row["action"] in {"CREATE", "SKIP", "UPDATE"}),
        "create": sum(1 for row in planned if row["action"] == "CREATE"),
        "skip": sum(1 for row in planned if row["action"] == "SKIP"),
        "update": sum(1 for row in planned if row["action"] == "UPDATE"),
        "conflict": sum(1 for row in planned if row["action"] == "CONFLICT"),
        "missing_device_user_id": missing_user_id,
        "duplicate_user_id": duplicate_user_id,
        "duplicate_card": duplicate_card,
        "conflict_with_new_device": sum(1 for row in planned if row["action"] == "CONFLICT"),
        "device_user_count": int(snapshot.get("user_count") or 0),
        "replacement_confirmed": bool(snapshot.get("replacement_confirmed")),
    }


def _require_inspect(device: Device) -> dict[str, Any]:
    snapshot = last_inspect_snapshot(device)
    if not snapshot:
        raise ReplacementHardwareError("Run inspect on the replacement device before preflight.")
    serial = inspect_snapshot_serial(snapshot)
    assert_replacement_hardware(device, serial=serial, require_serial=True)
    if not snapshot.get("connected"):
        raise ReplacementHardwareError(
            snapshot.get("connection_detail") or "Replacement device inspect did not connect."
        )
    return snapshot


def create_preflight(
    db: Session,
    device: Device,
    *,
    include_departed: bool = False,
    created_by: str | None = None,
) -> DeviceMigration:
    assert_replacement_hardware(device, require_serial=False)
    snapshot = _require_inspect(device)
    employees = _roster(db, include_departed=include_departed)
    planned = plan_actions(employees, snapshot)
    summary = _preflight_summary(employees, planned, snapshot)
    row = DeviceMigration(
        migration_uuid=str(uuid4()),
        device_id=device.name,
        status="PREFLIGHT",
        include_departed=include_departed,
        target_ip=device.ip_address,
        target_port=device.port,
        inspect_snapshot=snapshot,
        preflight_summary=summary,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def run_dry_run(
    db: Session,
    device: Device,
    *,
    include_departed: bool = False,
    created_by: str | None = None,
    migration_uuid: str | None = None,
) -> DeviceMigration:
    snapshot = _require_inspect(device)
    employees = _roster(db, include_departed=include_departed)
    planned = plan_actions(employees, snapshot)
    summary = _preflight_summary(employees, planned, snapshot)
    if migration_uuid:
        migration = get_migration(db, device.name, migration_uuid)
    else:
        migration = DeviceMigration(
            migration_uuid=str(uuid4()),
            device_id=device.name,
            include_departed=include_departed,
            target_ip=device.ip_address,
            target_port=device.port,
            created_by=created_by,
        )
        db.add(migration)
        db.flush()
    migration.inspect_snapshot = snapshot
    migration.preflight_summary = summary
    migration.target_ip = device.ip_address
    migration.target_port = device.port
    migration.include_departed = include_departed
    migration.status = "AWAITING_APPROVAL"
    migration.last_error = None
    for item in list(migration.items):
        db.delete(item)
    db.flush()
    for row in planned:
        db.add(
            DeviceMigrationItem(
                migration_id=migration.id,
                employee_id=int(row["employee_id"]),
                employee_uuid=str(row["employee_uuid"]),
                device_user_id=str(row["device_user_id"]),
                name=str(row["name"]),
                planned_uid=int(row["uid"]) if row.get("uid") is not None else None,
                card=str(row["card"]) if row.get("card") is not None else None,
                planned_action=str(row["action"]),
                conflict_reason=row.get("conflict"),
                status="PENDING" if row["action"] in {"CREATE", "UPDATE"} else row["action"],
            )
        )
    db.flush()
    return migration


def get_migration(db: Session, device_name: str, migration_uuid: str) -> DeviceMigration:
    row = db.execute(
        select(DeviceMigration)
        .options(selectinload(DeviceMigration.items))
        .where(
            DeviceMigration.migration_uuid == migration_uuid,
            DeviceMigration.device_id == device_name,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"Migration '{migration_uuid}' not found for device '{device_name}'.")
    return row


def migration_to_dict(migration: DeviceMigration, *, include_items: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "migration_id": migration.migration_uuid,
        "device_id": migration.device_id,
        "status": migration.status,
        "include_departed": migration.include_departed,
        "target_ip": migration.target_ip,
        "target_port": migration.target_port,
        "preflight_summary": migration.preflight_summary,
        "report": migration.report,
        "last_error": migration.last_error,
        "created_at": migration.created_at.isoformat() if migration.created_at else None,
        "started_at": migration.started_at.isoformat() if migration.started_at else None,
        "completed_at": migration.completed_at.isoformat() if migration.completed_at else None,
        "fingerprint_next_step": (
            "Employees must enroll fingerprints on the replacement terminal. "
            "Templates were never stored in PostgreSQL and the old device is retired."
        ),
    }
    if include_items:
        payload["items"] = [
            {
                "employee_id": item.employee_id,
                "employee_uuid": item.employee_uuid,
                "device_user_id": item.device_user_id,
                "name": item.name,
                "uid": item.assigned_uid if item.assigned_uid is not None else item.planned_uid,
                "card": item.card,
                "action": item.actual_action or item.planned_action,
                "planned_action": item.planned_action,
                "conflict": item.conflict_reason,
                "status": item.status,
                "command_uuid": item.command_uuid,
                "last_error": item.last_error,
            }
            for item in sorted(migration.items, key=lambda row: row.employee_id)
        ]
    return payload


def _live_snapshot_from_users(users: list[Any], *, serial: str | None) -> dict[str, Any]:
    rows = []
    for user in users:
        rows.append(
            {
                "uid": int(user.uid),
                "user_id": str(user.user_id).strip(),
                "name": user.name,
                "privilege": user.privilege,
                "group_id": user.group_id,
                "card": user.card,
            }
        )
    return {
        "connected": True,
        "users": rows,
        "user_count": len(rows),
        "serial_number": serial,
        "replacement_confirmed": True,
    }


def _assert_execute_confirmation(
    device: Device,
    *,
    confirm_target_device_name: str,
    confirm_target_ip: str,
) -> None:
    if confirm_target_device_name.strip() != device.name:
        raise ReplacementHardwareError(
            f"confirm_target_device_name must be '{device.name}'."
        )
    if confirm_target_ip.strip() != device.ip_address.strip():
        raise ReplacementHardwareError("confirm_target_ip must match the Settings IP for this device.")


def _apply_device_uid(db: Session, employee_id: int, uid: int | None) -> None:
    if uid is None or uid <= 0:
        return
    emp = db.get(Employee, employee_id)
    if emp is None:
        return
    emp.device_uid = int(uid)


def _execute_item(
    db: Session,
    *,
    item: DeviceMigrationItem,
    action: str,
    planned_uid: int | None,
    live_uid: int | None,
    device: Device,
    settings: Settings,
    initiated_by: str | None,
    correlation_id: str,
) -> None:
    item.actual_action = action
    if action == "SKIP":
        item.status = "SKIPPED"
        assigned = live_uid if live_uid is not None else planned_uid
        item.assigned_uid = assigned
        _apply_device_uid(db, item.employee_id, assigned)
        return
    if action == "CONFLICT":
        item.status = "CONFLICT"
        return
    if action not in {"CREATE", "UPDATE"}:
        item.status = "SKIPPED"
        return
    if ALLOWED_EXECUTE_COMMAND in MIGRATION_FORBIDDEN_COMMANDS:
        raise RuntimeError("UPSERT_USER must remain allowed for metadata migration.")
    emp = db.get(Employee, item.employee_id)
    payload = {
        "user_id": item.device_user_id,
        "name": item.name,
        "uid": planned_uid,
        "privilege": emp.device_privilege if emp is not None else 0,
        "group_id": emp.device_group_id if emp is not None else "",
        "card": emp.device_card if emp is not None else "0",
        "cutover_migration_id": correlation_id,
    }
    command = enqueue_device_command(
        db,
        device_id=device.name,
        command_type=ALLOWED_EXECUTE_COMMAND,
        payload=payload,
        correlation_id=correlation_id,
        created_by=initiated_by,
        initiated_from="migration:execute",
    )
    item.command_uuid = command.command_uuid
    process_command(db, command, settings=settings, worker_id="migration-inline")
    if command.status != "SUCCESS":
        item.status = "FAILED"
        item.last_error = command.last_error or "UPSERT_USER failed"
        return
    details = command.verification_details or {}
    actual = details.get("actual_state") if isinstance(details, dict) else None
    assigned = None
    if isinstance(actual, dict) and actual.get("uid") is not None:
        try:
            assigned = int(actual["uid"])
        except (TypeError, ValueError):
            assigned = planned_uid
    else:
        assigned = planned_uid
    item.assigned_uid = assigned
    item.verification_details = details if isinstance(details, dict) else None
    item.status = "SUCCESS"
    _apply_device_uid(db, item.employee_id, assigned)


def execute_migration(
    db: Session,
    device: Device,
    migration_uuid: str,
    *,
    confirm_target_device_name: str,
    confirm_target_ip: str,
    approved_by: str | None,
    approve_update_user_ids: list[str] | None = None,
    settings: Settings | None = None,
    retry_failed_only: bool = False,
) -> DeviceMigration:
    settings = settings or get_settings()
    _assert_execute_confirmation(
        device,
        confirm_target_device_name=confirm_target_device_name,
        confirm_target_ip=confirm_target_ip,
    )
    snapshot = _require_inspect(device)
    assert_replacement_hardware(device, serial=inspect_snapshot_serial(snapshot), require_serial=True)
    migration = get_migration(db, device.name, migration_uuid)
    if migration.status not in {"AWAITING_APPROVAL", "PARTIAL", "FAILED", "DRY_RUN", "RUNNING", "VERIFIED"}:
        if migration.status == "PREFLIGHT":
            raise ReplacementHardwareError("Run dry-run and approve before execute.")
    migration.approved_by = approved_by
    migration.started_at = migration.started_at or _utcnow()
    migration.status = "RUNNING"
    migration.last_error = None
    db.flush()

    service = device_service_for(db, device_name=device.name, settings=settings)
    try:
        with device_session_lock(device.name, settings, blocking_timeout=90):
            live_users = service.fetch_users()
    except DeviceLockContentionError as exc:
        migration.status = "FAILED"
        migration.last_error = str(exc)
        migration.completed_at = _utcnow()
        db.flush()
        return migration
    except Exception as exc:  # noqa: BLE001
        migration.status = "FAILED"
        migration.last_error = format_device_connection_error(exc, settings=settings)
        migration.completed_at = _utcnow()
        db.flush()
        return migration

    live_snapshot = _live_snapshot_from_users(live_users, serial=inspect_snapshot_serial(snapshot))
    live_by_user_id = _users_by_id(live_snapshot)
    employees = _roster(db, include_departed=migration.include_departed)
    by_emp = {emp.id: emp for emp in employees}
    approved = set(approve_update_user_ids or [])
    planned_map = {
        int(row["employee_id"]): row
        for row in plan_actions(employees, live_snapshot, approve_update_user_ids=approved)
    }

    items = list(migration.items)
    if retry_failed_only:
        items = [item for item in items if item.status in {"FAILED", "PENDING"}]

    create_items: list[DeviceMigrationItem] = []
    for item in items:
        emp = by_emp.get(item.employee_id)
        if emp is None:
            item.status = "SKIPPED"
            item.actual_action = "SKIP"
            item.last_error = "Employee not in migration roster"
            continue
        row = planned_map.get(item.employee_id)
        action = str(row["action"]) if row else "SKIP"
        planned_uid = int(row["uid"]) if row and row.get("uid") is not None else item.planned_uid
        live_uid = None
        live_row = live_by_user_id.get(item.device_user_id)
        if live_row and live_row.get("uid") is not None:
            try:
                live_uid = int(live_row["uid"])
            except (TypeError, ValueError):
                live_uid = None
        item.conflict_reason = row.get("conflict") if row else item.conflict_reason
        if action == "CREATE":
            item.actual_action = "CREATE"
            item.planned_uid = planned_uid
            create_items.append(item)
            continue
        try:
            with db.begin_nested():
                _execute_item(
                    db,
                    item=item,
                    action=action,
                    planned_uid=planned_uid,
                    live_uid=live_uid,
                    device=device,
                    settings=settings,
                    initiated_by=approved_by,
                    correlation_id=migration.migration_uuid,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Migration item failed user_id=%s: %s", item.device_user_id, exc)
            item.status = "FAILED"
            item.actual_action = action
            item.last_error = str(exc)

    if create_items:
        bulk_rows = []
        for item in create_items:
            emp = by_emp.get(item.employee_id)
            bulk_rows.append(
                {
                    "user_id": item.device_user_id,
                    "name": item.name,
                    "uid": item.planned_uid,
                    "privilege": emp.device_privilege if emp is not None else 0,
                    "group_id": emp.device_group_id if emp is not None else "",
                    "card": emp.device_card if emp is not None else "0",
                }
            )
        try:
            with device_session_lock(device.name, settings, blocking_timeout=90):
                bulk = service.create_missing_users(bulk_rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bulk CREATE failed: %s", exc)
            for item in create_items:
                item.status = "FAILED"
                item.last_error = format_device_connection_error(exc, settings=settings)
            bulk = {"created": [], "skipped": [], "failed": [], "users": []}
        created_by_id = {row["user_id"]: row for row in bulk.get("created") or []}
        skipped_by_id = {row["user_id"]: row for row in bulk.get("skipped") or []}
        failed_by_id = {row["user_id"]: row for row in bulk.get("failed") or []}
        live_after = {str(row.get("user_id") or "").strip(): row for row in bulk.get("users") or []}
        for item in create_items:
            if item.status == "FAILED":
                continue
            user_id = item.device_user_id
            if user_id in failed_by_id:
                item.status = "FAILED"
                item.last_error = str(failed_by_id[user_id].get("error") or "CREATE failed")
                continue
            assigned = None
            source = created_by_id.get(user_id) or skipped_by_id.get(user_id) or live_after.get(user_id)
            if source and source.get("uid") is not None:
                try:
                    assigned = int(source["uid"])
                except (TypeError, ValueError):
                    assigned = item.planned_uid
            else:
                assigned = item.planned_uid
            item.assigned_uid = assigned
            item.status = "SKIPPED" if user_id in skipped_by_id else "SUCCESS"
            if user_id in skipped_by_id:
                item.actual_action = "SKIP"
            _apply_device_uid(db, item.employee_id, assigned)
            logger.info("Migration item user_id=%s action=%s status=%s", user_id, item.actual_action, item.status)

    statuses = {item.status for item in migration.items}
    failed = "FAILED" in statuses
    success_writes = any(item.status == "SUCCESS" for item in migration.items)
    if failed:
        migration.status = "PARTIAL" if success_writes else "FAILED"
    else:
        migration.status = "VERIFIED"
    migration.completed_at = _utcnow()
    migration.report = _build_report(migration)
    db.flush()
    return migration


def retry_failed(
    db: Session,
    device: Device,
    migration_uuid: str,
    *,
    confirm_target_device_name: str,
    confirm_target_ip: str,
    approved_by: str | None,
    settings: Settings | None = None,
) -> DeviceMigration:
    return execute_migration(
        db,
        device,
        migration_uuid,
        confirm_target_device_name=confirm_target_device_name,
        confirm_target_ip=confirm_target_ip,
        approved_by=approved_by,
        settings=settings,
        retry_failed_only=True,
    )


def _build_report(migration: DeviceMigration) -> dict[str, Any]:
    items = list(migration.items)
    return {
        "totals": {
            "items": len(items),
            "create_success": sum(1 for i in items if i.actual_action == "CREATE" and i.status == "SUCCESS"),
            "update_success": sum(1 for i in items if i.actual_action == "UPDATE" and i.status == "SUCCESS"),
            "skipped": sum(1 for i in items if i.status in {"SKIPPED", "SKIP"}),
            "conflicts": sum(1 for i in items if i.status == "CONFLICT"),
            "failed": sum(1 for i in items if i.status == "FAILED"),
        },
        "failed_user_ids": [i.device_user_id for i in items if i.status == "FAILED"],
        "conflict_user_ids": [i.device_user_id for i in items if i.status == "CONFLICT"],
        "fingerprint_next_step": (
            "Employees must enroll fingerprints on the replacement terminal."
        ),
    }
