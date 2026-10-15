"""SQLAlchemy engine, session factory, and dependency helpers."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import Settings, get_settings

settings = get_settings()


def postgres_connect_args(cfg: Settings) -> dict[str, Any]:
    """libpq options shared by the app, Alembic, and the startup preflight.

    connect_timeout stops a dead DB host from hanging requests for minutes, and TCP
    keepalives let both sides notice connections silently dropped by firewalls/NAT
    between the app VM and the database host.
    """
    return {
        "connect_timeout": cfg.db_connect_timeout_seconds,
        "application_name": cfg.db_application_name,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }


def _engine_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": settings.db_pool_recycle_seconds,
    }
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
        return kwargs
    kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        # LIFO keeps a few hot connections busy so idle extras age out instead of all going stale.
        pool_use_lifo=True,
    )
    if url.startswith("postgresql"):
        kwargs["connect_args"] = postgres_connect_args(settings)
    return kwargs


_db_url = str(settings.database_url)
engine: Engine = create_engine(_db_url, **_engine_kwargs(_db_url))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Optional read replica — falls back to primary when DATABASE_READ_URL is unset.
_read_url = settings.database_read_url
if _read_url and str(_read_url) != _db_url and not str(_read_url).startswith("sqlite"):
    read_engine: Engine = create_engine(str(_read_url), **_engine_kwargs(str(_read_url)))
else:
    read_engine = engine

ReadSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=read_engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_read_db() -> Generator[Session, None, None]:
    """Yield a session bound to the read replica (or primary if none configured)."""
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engines() -> None:
    """Dispose connection pools (graceful shutdown)."""
    engine.dispose()
    if read_engine is not engine:
        read_engine.dispose()
