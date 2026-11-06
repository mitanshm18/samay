"""Database settings: local only, and the password is never shown."""

from __future__ import annotations

import pytest

from samay.db.config import DatabaseConfigError, database_url


def test_built_from_env_values() -> None:
    url = database_url({"SAMAY_DB_PASSWORD": "pw", "SAMAY_DB_PORT": "55433"})
    assert (url.host, url.port, url.username, url.database) == (
        "127.0.0.1",
        55433,
        "samay",
        "samay",
    )
    assert url.drivername == "postgresql+psycopg"
    assert "pw" not in str(url)


def test_default_port() -> None:
    assert database_url({"SAMAY_DB_PASSWORD": "pw"}).port == 55432
    assert database_url({"SAMAY_DB_PASSWORD": "pw", "SAMAY_DB_PORT": " "}).port == 55432


def test_explicit_url_wins() -> None:
    url = database_url(
        {"SAMAY_DATABASE_URL": "postgresql+psycopg://u:p@localhost:5/x", "SAMAY_DB_PASSWORD": ""}
    )
    assert (url.host, url.database) == ("localhost", "x")


def test_reads_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAMAY_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:5/env")
    assert database_url().database == "env"


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "SAMAY_DB_PASSWORD is not set"),
        ({"SAMAY_DB_PASSWORD": "pw", "SAMAY_DB_PORT": "abc"}, "port number"),
        ({"SAMAY_DB_PASSWORD": "pw", "SAMAY_DB_PORT": "70000"}, "port number"),
        ({"SAMAY_DB_PASSWORD": "pw", "SAMAY_DB_PORT": "0"}, "port number"),
        ({"SAMAY_DATABASE_URL": "::not a url::"}, "not a valid database URL"),
        ({"SAMAY_DATABASE_URL": "sqlite:///x.db"}, r"only uses postgresql\+psycopg"),
        ({"SAMAY_DATABASE_URL": "postgresql+psycopg://u:secret@db.example.com/x"}, "not host"),
        ({"SAMAY_DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:5"}, "names no database"),
    ],
)
def test_refused(env: dict[str, str], message: str) -> None:
    with pytest.raises(DatabaseConfigError, match=message) as caught:
        database_url(env)
    assert "secret" not in str(caught.value)
