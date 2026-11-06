"""Where SAMAY's database is. Local only: SAMAY never connects to another host.

SAMAY_DATABASE_URL wins if set (CI uses it). Otherwise the URL is built from the
same .env values compose.yaml uses: SAMAY_DB_PASSWORD and SAMAY_DB_PORT.
The password is never printed: errors and str() use a masked URL.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

DRIVER = "postgresql+psycopg"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_PORT = 55432


class DatabaseConfigError(ValueError):
    """The database settings are missing or point somewhere SAMAY must not go."""


def database_url(environ: Mapping[str, str] | None = None) -> URL:
    env = os.environ if environ is None else environ
    raw = env.get("SAMAY_DATABASE_URL", "").strip()
    if raw:
        try:
            url = make_url(raw)
        except ArgumentError:
            raise DatabaseConfigError("SAMAY_DATABASE_URL is not a valid database URL") from None
    else:
        password = env.get("SAMAY_DB_PASSWORD", "")
        if not password:
            raise DatabaseConfigError(
                "SAMAY_DB_PASSWORD is not set: copy .env.example to .env and set it"
            )
        port_text = env.get("SAMAY_DB_PORT", "").strip() or str(DEFAULT_PORT)
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            raise DatabaseConfigError(f"SAMAY_DB_PORT must be a port number, got {port_text!r}")
        url = URL.create(
            DRIVER,
            username="samay",
            password=password,
            host="127.0.0.1",
            port=int(port_text),
            database="samay",
        )
    if url.drivername != DRIVER:
        raise DatabaseConfigError(f"SAMAY only uses {DRIVER}, got {url.drivername!r}")
    if url.host not in LOCAL_HOSTS:
        raise DatabaseConfigError(
            f"SAMAY only connects to its own local database, not host {url.host!r}"
        )
    if not url.database:
        raise DatabaseConfigError("the database URL names no database")
    return url
