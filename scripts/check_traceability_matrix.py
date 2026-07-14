#!/usr/bin/env python3
"""Verify TRACEABILITY_MATRIX.md surfaces are present and testids appear in the suite."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "testing" / "TRACEABILITY_MATRIX.md"
BACKEND_TESTS = ROOT / "backend" / "tests"
FRONTEND_SRC = ROOT / "frontend" / "src"
FRONTEND_TESTS = ROOT / "frontend" / "tests"
E2E_DIR = ROOT / "e2e"
BACKEND_APP = ROOT / "backend" / "app"


def _matrix_testids() -> set[str]:
    text = MATRIX.read_text(encoding="utf-8")
    return set(re.findall(r"\b(?:BE|FE|E2E)-[A-Z0-9]+(?:-[A-Z0-9]+)+\b", text))


def _collect_python_testids() -> set[str]:
    found: set[str] = set()
    for path in BACKEND_TESTS.rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name == "testid" and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.add(arg.value)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "testid"
                        and dec.args
                        and isinstance(dec.args[0], ast.Constant)
                    ):
                        found.add(str(dec.args[0].value))
    return found


def _collect_frontend_testids() -> set[str]:
    found: set[str] = set()
    pattern = re.compile(r"FE-UNIT-[A-Z0-9-]+")
    roots = [FRONTEND_TESTS, FRONTEND_SRC]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.test.*"):
            found.update(pattern.findall(path.read_text(encoding="utf-8")))
            found.update(pattern.findall(path.name))
    return found


def _collect_e2e_testids() -> set[str]:
    found: set[str] = set()
    pattern = re.compile(r"E2E-[A-Z0-9-]+")
    if not E2E_DIR.exists():
        return found
    for path in E2E_DIR.rglob("*.ts"):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def _fastapi_paths() -> set[str]:
    """Discover routes via OpenAPI (works with FastAPI _IncludedRouter)."""
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.main import app

        schema = app.openapi()
        paths: set[str] = set()
        for path, methods in (schema.get("paths") or {}).items():
            for method in methods:
                if method.upper() in {"HEAD", "OPTIONS", "PARAMETERS"}:
                    continue
                if method.startswith("x-"):
                    continue
                paths.add(f"{method.upper()} {path}")
        return paths
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not import FastAPI app for route discovery: {exc}")
        return set()


def _pages() -> set[str]:
    pages = FRONTEND_SRC / "pages"
    if not pages.exists():
        return set()
    return {p.stem for p in pages.glob("*.tsx") if not p.name.endswith(".test.tsx")}


def main() -> int:
    if not MATRIX.exists():
        print(f"ERROR: missing {MATRIX}")
        return 1

    matrix_ids = _matrix_testids()
    impl_ids = _collect_python_testids() | _collect_frontend_testids() | _collect_e2e_testids()

    # Filter to "required" IDs that look like suite markers (exclude UNIMPLEMENTED noise)
    required = {i for i in matrix_ids if i.startswith(("BE-", "FE-", "E2E-"))}
    missing = sorted(required - impl_ids)

    print(f"Matrix test IDs: {len(required)}")
    print(f"Implemented test IDs: {len(impl_ids & required)}")

    pages = _pages()
    for page in sorted(pages):
        # Matrix mentions page names; soft check
        if page not in MATRIX.read_text(encoding="utf-8"):
            print(f"WARN: page {page} not mentioned in matrix")

    routes = _fastapi_paths()
    if routes:
        print(f"Discovered FastAPI routes: {len(routes)}")

    # Strict: every matrix ID should appear in code (comments, markers, or annotations)
    # Allow a small set of alias duplicates already covered by parent IDs
    soft_ok_prefixes = ()
    hard_missing = [m for m in missing if not any(m.startswith(p) for p in soft_ok_prefixes)]

    if hard_missing:
        print(f"ERROR: {len(hard_missing)} matrix test IDs not found in suite:")
        for item in hard_missing[:50]:
            print(f"  - {item}")
        if len(hard_missing) > 50:
            print(f"  ... and {len(hard_missing) - 50} more")
        return 1

    print("OK: traceability matrix IDs are present in the automated suite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
