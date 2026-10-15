"""Unit tests for database read replica helpers."""

from __future__ import annotations

import pytest

from app.core import database as dbmod


@pytest.mark.testid("BE-UNIT-DB-001")
def test_read_engine_falls_back_to_primary() -> None:
    # In tests, DATABASE_READ_URL is unset so read_engine == engine.
    assert dbmod.read_engine is dbmod.engine


@pytest.mark.testid("BE-UNIT-DB-002")
def test_get_read_db_yields_session() -> None:
    gen = dbmod.get_read_db()
    session = next(gen)
    try:
        assert session is not None
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


@pytest.mark.testid("BE-UNIT-DB-003")
def test_postgres_connect_args_fail_fast_and_keep_alive() -> None:
    from app.core.config import get_settings

    args = dbmod.postgres_connect_args(get_settings())
    assert args["connect_timeout"] >= 2
    assert args["keepalives"] == 1
    assert args["keepalives_idle"] > 0
    assert args["application_name"]
