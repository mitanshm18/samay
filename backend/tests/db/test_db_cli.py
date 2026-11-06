"""python -m samay.db save|list|show|verify, against a test database."""

from __future__ import annotations

import io
import json

import pytest
from dbhelpers import EXAMPLES, example
from sqlalchemy import Engine

from samay.db import __main__ as db_cli
from samay.db import save_bill
from samay.io import json_report


@pytest.fixture
def use_db(db: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    url = db.url.render_as_string(hide_password=False)
    monkeypatch.setenv("SAMAY_DATABASE_URL", url)
    return db


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = db_cli.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_save_list_show_verify(use_db: Engine) -> None:
    code, out, _ = run("save", str(EXAMPLES / "differing.json"))
    assert code == 1  # differences found, as in samay.cli reconcile
    assert "SYNTHETIC" in out
    assert "Saved (new bill file): #1" in out
    assert "printed ₹" in out
    assert "explanation" in out

    code, out, _ = run("save", "--calculate-only", str(EXAMPLES / "missing-data.json"))
    assert code == 0
    assert "total MISSING" in out

    code, out, _ = run("save", str(EXAMPLES / "differing.json"))
    assert "bill file already saved" in out

    code, out, _ = run("list")
    assert code == 0
    assert [line.split()[0] for line in out.splitlines()] == ["#3", "#2", "#1"]
    code, out, _ = run("list", "--limit", "1")
    assert out.count("\n") == 1

    code, out, _ = run("show", "1")
    assert code == 0
    assert json.loads(out)["command"] == "reconcile"
    code, out, _ = run("show", "1", "--source")
    assert out.encode("utf-8") == example("differing.json")

    code, out, _ = run("verify", "1")
    assert code == 0
    assert "identical" in out


def test_matching_bill_exits_0(use_db: Engine) -> None:
    code, _, _ = run("save", str(EXAMPLES / "matching.json"))
    assert code == 0


def test_empty_list(use_db: Engine) -> None:
    code, out, _ = run("list")
    assert (code, out) == (0, "No saved runs yet.\n")


def test_verify_difference_exits_1(use_db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    save_bill(use_db, example("differing.json"))
    real = json_report.dumps
    monkeypatch.setattr(json_report, "dumps", lambda doc: real(doc) + " ")
    code, out, _ = run("verify", "1")
    assert code == 1
    assert "DIFFERS" in out
    assert "unchanged" in out


def test_invalid_bill_exits_2_and_saves_nothing(use_db: Engine) -> None:
    code, _, err = run("save", "/nonexistent/bill.json")
    assert code == 2
    assert "cannot-read-file" in err
    code, out, _ = run("list")
    assert out == "No saved runs yet.\n"


def test_unknown_run_exits_2(use_db: Engine) -> None:
    code, _, err = run("show", "42")
    assert code == 2
    assert "no saved run with id 42" in err


def test_limit_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        run("list", "--limit", "0")


def test_missing_settings_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAMAY_DATABASE_URL", raising=False)
    monkeypatch.delenv("SAMAY_DB_PASSWORD", raising=False)
    code, _, err = run("list")
    assert code == 2
    assert "SAMAY_DB_PASSWORD" in err


def test_unreachable_database_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SAMAY_DATABASE_URL", "postgresql+psycopg://samay:x@127.0.0.1:1/samay?connect_timeout=2"
    )
    code, _, err = run("list")
    assert code == 3
    assert "make db-up" in err
    assert ":x@" not in err


def test_internal_error_exits_3(use_db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(db_cli, "list_runs", broken)
    code, _, err = run("list")
    assert code == 3
    assert "internal error: RuntimeError: boom" in err
