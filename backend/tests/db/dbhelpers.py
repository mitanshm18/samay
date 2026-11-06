"""Helpers shared by the database tests (tests/db is on sys.path under pytest)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

BACKEND = Path(__file__).resolve().parents[2]
EXAMPLES = BACKEND.parent / "examples" / "bills"
GOLDEN = BACKEND / "tests" / "golden"


def alembic_config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


def migrate(url: URL, revision: str = "head", *, down: bool = False) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            if down:
                command.downgrade(config, revision)
            else:
                command.upgrade(config, revision)
    finally:
        engine.dispose()


def example(name: str) -> bytes:
    return (EXAMPLES / name).read_bytes()
