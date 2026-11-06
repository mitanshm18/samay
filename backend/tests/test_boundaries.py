"""The calculation engine never depends on the database (decision 0005).

core, tariffs, billing, io and the bill command line must not import
SQLAlchemy, psycopg, Alembic or samay.db, so they stay pure and testable
without any server. core stays standard-library only.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

import samay

SRC = Path(__file__).resolve().parents[1] / "src" / "samay"
ENGINE = [*(SRC / p for p in ("core", "tariffs", "billing", "io")), SRC / "cli.py"]
FORBIDDEN = ("sqlalchemy", "psycopg", "alembic", "samay.db")


def _files() -> list[Path]:
    files: list[Path] = []
    for path in ENGINE:
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def _imports(path: Path) -> list[str]:
    package = ".".join(path.relative_to(SRC.parent).with_suffix("").parts[:-1])
    return _imports_in(path.read_text("utf-8"), package)


def _imports_in(source: str, package: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                module = f"{base}.{node.module}" if node.module else base
                names.append(module)
                names.extend(f"{module}.{alias.name}" for alias in node.names)
            else:
                names.append(node.module or "")
    return names


@pytest.mark.parametrize("path", _files(), ids=lambda p: str(p.relative_to(SRC)))
def test_engine_does_not_import_the_database(path: Path) -> None:
    bad = [
        name
        for name in _imports(path)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
    ]
    assert bad == []


def test_core_uses_only_the_standard_library() -> None:
    for path in sorted((SRC / "core").rglob("*.py")):
        for name in _imports(path):
            top = name.split(".")[0]
            assert top == "samay" or top in sys.stdlib_module_names, (path.name, name)


def test_the_scan_sees_relative_imports() -> None:
    """Guard the guard: a relative import of samay.db would be caught."""
    names = _imports_in("from ..db import store\nfrom . import inputs\n", "samay.billing")
    assert "samay.db.store" in names
    assert "samay.billing.inputs" in names


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((SRC.parents[1] / "pyproject.toml").read_text("utf-8"))
    assert samay.__version__ == pyproject["project"]["version"]
