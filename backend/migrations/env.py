"""Alembic environment. Online mode only: SAMAY never writes SQL scripts to run
by hand. A connection passed in config.attributes["connection"] (used by the
tests) is used as is; otherwise the URL comes from samay.db.config."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, create_engine

from samay.db.config import database_url
from samay.db.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(database_url())
    try:
        with engine.connect() as fresh:
            _run(fresh)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise SystemExit("SAMAY runs migrations online only: make db-migrate")
run_migrations_online()
