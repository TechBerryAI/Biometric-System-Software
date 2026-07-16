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
