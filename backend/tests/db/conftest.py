"""Database test fixtures (make backend-db-test).

Every test gets its own throwaway database, samay_test_<random>, cloned from a
migrated template inside SAMAY's own server (samay-db, or the CI service). The
`samay` database itself is never touched, and every test database is dropped.
The connection comes from samay.db.config: SAMAY_DATABASE_URL or .env values.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator

import pytest
from dbhelpers import migrate
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from samay.db.config import database_url


class Server:
    """Creates and drops samay_test_* databases on SAMAY's server."""

    def __init__(self, url: URL) -> None:
        self.url = url
        self.admin = create_engine(url, isolation_level="AUTOCOMMIT")

    def create(self, template: str | None = None) -> URL:
        name = f"samay_test_{secrets.token_hex(6)}"
        clause = f" TEMPLATE {template}" if template else ""
        with self.admin.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {name}{clause}"))
        return self.url.set(database=name)

    def drop(self, url: URL) -> None:
        name = url.database
        assert name is not None
        assert name.startswith("samay_test_")
        with self.admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


@pytest.fixture(scope="session")
def server() -> Iterator[Server]:
    created = Server(database_url())
    yield created
    created.admin.dispose()


@pytest.fixture(scope="session")
def template(server: Server) -> Iterator[str]:
    url = server.create()
    migrate(url)
    assert url.database is not None
    yield url.database
    server.drop(url)


@pytest.fixture
def empty_url(server: Server) -> Iterator[URL]:
    """A fresh database with no tables (for migration tests)."""
    url = server.create()
    yield url
    server.drop(url)


@pytest.fixture
def db(server: Server, template: str) -> Iterator[Engine]:
    """A fresh, fully migrated database for one test."""
    url = server.create(template)
    engine = create_engine(url)
    yield engine
    engine.dispose()
    server.drop(url)
