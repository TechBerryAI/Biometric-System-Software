"""Smoke tests: scripts parse / import without executing device I/O."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _assert_script_parses(filename: str) -> None:
    path = SCRIPTS_DIR / filename
    assert path.is_file(), f"missing script: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assert isinstance(tree, ast.Module)
    assert any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom)) for node in tree.body)


@pytest.mark.testid("BE-UNIT-SCR-001")
def test_sync_from_device_parses() -> None:
    _assert_script_parses("sync_from_device.py")


@pytest.mark.testid("BE-UNIT-SCR-002")
def test_probe_device_attlog_tier_parses() -> None:
    _assert_script_parses("probe_device_attlog_tier.py")


@pytest.mark.testid("BE-UNIT-SCR-003")
def test_restore_device_normal_mode_parses() -> None:
    _assert_script_parses("restore_device_normal_mode.py")


@pytest.mark.testid("BE-UNIT-SCR-004")
def test_purge_departed_employees_parses() -> None:
    _assert_script_parses("purge_departed_employees.py")
