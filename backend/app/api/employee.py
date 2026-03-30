"""Employee HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.employee import Employee
from app.schemas.employee import EmployeeCreate, EmployeeRead

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeRead])
def list_employees(db: Session = Depends(get_db)) -> list[Employee]:
    return list(db.execute(select(Employee).order_by(Employee.id)).scalars().all())


@router.post("", response_model=EmployeeRead)
def upsert_employee_metadata(payload: EmployeeCreate, db: Session = Depends(get_db)) -> Employee:
    """
    Create or update employee metadata in DB only (does not push to device).
    device_user_id must match the terminal user id.
    """
    existing = db.execute(
        select(Employee).where(Employee.device_user_id == payload.device_user_id)
    ).scalar_one_or_none()
    if existing is not None:
        existing.name = payload.name
        existing.department = payload.department
        existing.shift_start = payload.shift_start
        existing.shift_end = payload.shift_end
        db.commit()
        db.refresh(existing)
        return existing
    emp = Employee(
        device_user_id=payload.device_user_id,
        name=payload.name,
        department=payload.department,
        shift_start=payload.shift_start,
        shift_end=payload.shift_end,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp
