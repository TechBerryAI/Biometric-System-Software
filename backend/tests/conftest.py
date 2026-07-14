"""Pytest fixtures — set env before importing the app."""

from __future__ import annotations

import os
from collections.abc import Generator

# Must run before app.core.database is imported elsewhere.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-not-for-prod")
os.environ.setdefault("AUTH_BOOTSTRAP_ADMIN_EMAIL", "bootstrap@example.com")
os.environ.setdefault("AUTH_BOOTSTRAP_ADMIN_PASSWORD", "Bootstrap123!")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("XAI_API_KEY", "")
os.environ.setdefault("DEVICE_AUTO_SYNC_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models import (  # noqa: F401 — register metadata
    AttendanceLog,
    AttendanceSession,
    Device,
    DeviceCommand,
    DeviceUserMapping,
    Employee,
    RefreshToken,
    SystemControlState,
    User,
)
from tests.factories import make_operator, make_user

get_settings.cache_clear()


# Teach SQLite how to render JSONB columns.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # type: ignore[no-untyped-def]
    return "JSON"


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    from app.main import app

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    user = make_user(email="admin@example.com", role="SUPER_ADMIN")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def operator_user(db_session: Session) -> User:
    user = make_operator(email="operator@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def hr_user(db_session: Session) -> User:
    user = make_user(email="hr@example.com", role="HR_ADMIN")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def viewer_user(db_session: Session) -> User:
    user = make_user(email="viewer@example.com", role="VIEWER")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_header_for(user: User) -> dict[str, str]:
    token, _ = create_access_token(user_uuid=user.user_uuid, role=user.role, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(admin_user: User) -> dict[str, str]:
    return auth_header_for(admin_user)


@pytest.fixture()
def operator_headers(operator_user: User) -> dict[str, str]:
    return auth_header_for(operator_user)


@pytest.fixture()
def hr_headers(hr_user: User) -> dict[str, str]:
    return auth_header_for(hr_user)


@pytest.fixture()
def simulated_device():
    from tests.mocks.pyzk_simulator import SimulatedPyZKDevice

    device = SimulatedPyZKDevice()
    device.set_user(user_id="TBI001", name="Unmesh Tari", uid=1)
    device.add_attendance("TBI001", punch=0, status=0)
    return device
