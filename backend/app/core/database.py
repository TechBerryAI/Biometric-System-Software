"""SQLAlchemy engine, session factory, and dependency helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_db_url = str(settings.database_url)
_engine_kwargs: dict = {
    "pool_pre_ping": True,
    "pool_recycle": settings.db_pool_recycle_seconds,
}
if _db_url.startswith("sqlite"):
    from sqlalchemy.pool import StaticPool

    _engine_kwargs.update(
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )

engine: Engine = create_engine(_db_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Optional read replica — falls back to primary when DATABASE_READ_URL is unset.
_read_url = settings.database_read_url
if _read_url and str(_read_url) != _db_url and not str(_read_url).startswith("sqlite"):
    read_engine: Engine = create_engine(
        str(_read_url),
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
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
