"""Alembic environment: uses DATABASE_URL from backend/.env via app settings."""

from __future__ import annotations

import os
import sys
import time
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import OperationalError

# backend/ is cwd when running `alembic` from backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, postgres_connect_args  # noqa: E402
import app.models  # noqa: E402, F401  # registers metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", str(settings.database_url).replace("%", "%%"))

target_metadata = Base.metadata

# A database that is restarting drops new connections for a few seconds; retry briefly
# instead of failing the whole deploy. Real misconfiguration still fails after the last try.
_CONNECT_ATTEMPTS = max(1, int(os.getenv("MIGRATION_CONNECT_ATTEMPTS", "5")))


def run_migrations_offline() -> None:
    url = str(settings.database_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine_kwargs: dict[str, object] = {"poolclass": pool.NullPool}
    if str(settings.database_url).startswith("postgresql"):
        engine_kwargs["connect_args"] = {**postgres_connect_args(settings), "application_name": "biometrica-migrate"}
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        **engine_kwargs,
    )
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            connection = connectable.connect()
            break
        except OperationalError as exc:
            if attempt == _CONNECT_ATTEMPTS:
                raise
            delay = min(2**attempt, 15)
            reason = str(exc.orig).strip().splitlines()[0] if exc.orig else str(exc)
            print(
                f"[alembic] database connection failed (attempt {attempt}/{_CONNECT_ATTEMPTS}): {reason}; "
                f"retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    with connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
