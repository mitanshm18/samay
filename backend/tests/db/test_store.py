"""Saving and reading bills: exact round trip, golden values, immutability."""

from __future__ import annotations

import importlib.util
import io
import json
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from dbhelpers import EXAMPLES, GOLDEN, example
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError, InternalError
from sqlalchemy.orm import Session

from samay import cli
from samay.core import DataStatus, Traced
from samay.db import (
    BillDocument,
    CalculationRun,
    RunNotFoundError,
    get_run,
    list_runs,
    save_bill,
    store,
    verify_run,
)
from samay.io import BillInputError, json_report

EXAMPLE_FILES = sorted(p.name for p in EXAMPLES.glob("*.json"))


def _golden() -> ModuleType:
    spec = importlib.util.spec_from_file_location("golden_bills", GOLDEN / "test_golden.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cli_json(path: Path, command: str) -> str:
    out = io.StringIO()
    cli.main([command, str(path), "--format", "json"], out=out, err=io.StringIO())
    return out.getvalue()


def _counts(db: Engine) -> tuple[int, int]:
    with Session(db) as session:
        documents = session.execute(select(func.count()).select_from(BillDocument)).scalar_one()
        runs = session.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    return documents, runs


def _paise(node: dict[str, Any] | None) -> int | None:
    return None if node is None or node["value"] is None else int(node["paise"])


@pytest.mark.parametrize("name", EXAMPLE_FILES)
@pytest.mark.parametrize("command", ["calculate", "reconcile"])
def test_saved_report_is_exactly_the_command_line_output(
    db: Engine, name: str, command: str
) -> None:
    data = example(name)
    saved = save_bill(db, data, command)
    stored = get_run(db, saved.run_id)
    assert stored.source_bytes == data
    assert stored.report_text == _cli_json(EXAMPLES / name, command)
    report = json.loads(stored.report_text)
    summary = stored.summary
    assert summary.exit_code == int(report["exit_code"]) == saved.exit_code
    assert summary.calculated_total_paise == _paise(report["calculation"]["total"])
    assert summary.tariff_status == "synthetic"
    assert report["synthetic"] is True
    if command == "reconcile":
        total = report["reconciliation"]["total"]
        assert summary.printed_total_paise == _paise(total.get("printed"))
        assert summary.total_difference_paise == _paise(total["difference"])
        assert summary.explanation == report["reconciliation"]["explanation"]["state"].lower()
    else:
        assert summary.printed_total_paise is None
        assert summary.explanation is None


@pytest.mark.parametrize("bill_id", ["GB1", "GB2", "GB3"])
def test_golden_bills_save_with_the_hand_checked_values(db: Engine, bill_id: str) -> None:
    golden = _golden()
    signed = golden.signed(bill_id)
    calc, recon = signed["calculation"], signed["reconciliation"]
    data = golden.input_json(bill_id)
    data["printed"] = golden.printed_variant(bill_id, calc)
    saved = save_bill(db, json.dumps(data).encode("utf-8"))
    stored = get_run(db, saved.run_id)

    def want(value: str) -> int | None:
        return None if value in (golden.MISSING, golden.UNDETERMINED) else int(value)

    summary = stored.summary
    assert summary.calculated_total_paise == want(calc["total_paise"])
    assert summary.calculated_total_paise == want(recon["calculated_total_paise"])
    assert summary.printed_total_paise == want(recon["printed_total_paise"])
    assert summary.total_difference_paise == want(recon["total_difference_paise"])
    assert summary.explanation == recon["explanation"].lower()
    assert str(summary.exit_code) == recon["exit_code"]
    lines = json.loads(stored.report_text)["reconciliation"]["lines"]
    assert {line["code"]: line["status"] for line in lines} == {
        code: item["status"] for code, item in recon["lines"].items()
    }
    assert verify_run(db, saved.run_id).matches


def test_missing_total_is_null_never_zero(db: Engine) -> None:
    saved = save_bill(db, example("missing-data.json"))
    with db.connect() as connection:
        row = connection.execute(
            text(
                "SELECT calculated_total_paise, total_difference_paise FROM calculation_run"
                " WHERE id = :id"
            ),
            {"id": saved.run_id},
        ).one()
    assert row.calculated_total_paise is None
    assert row.total_difference_paise is None


def test_same_file_is_stored_once_and_each_save_is_a_new_run(db: Engine) -> None:
    first = save_bill(db, example("matching.json"))
    second = save_bill(db, example("matching.json"))
    assert first.document_was_new
    assert not second.document_was_new
    assert first.bill_document_id == second.bill_document_id
    assert second.run_id > first.run_id
    assert _counts(db) == (1, 2)


def test_invalid_bill_saves_nothing(db: Engine) -> None:
    with pytest.raises(BillInputError):
        save_bill(db, b'{"format": "samay.bill/1"}')
    with pytest.raises(BillInputError):
        save_bill(db, b"not json")
    assert _counts(db) == (0, 0)


def test_unknown_command_saves_nothing(db: Engine) -> None:
    with pytest.raises(ValueError, match="command must be one of"):
        save_bill(db, example("matching.json"), "adjust")
    assert _counts(db) == (0, 0)


def test_failed_run_insert_rolls_back_the_document(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bytes] = []
    real = store._sha256

    def second_call_breaks(data: bytes) -> str:
        calls.append(data)
        return real(data) if len(calls) == 1 else "not-a-sha"

    monkeypatch.setattr(store, "_sha256", second_call_breaks)
    with pytest.raises(IntegrityError):
        save_bill(db, example("matching.json"))
    assert _counts(db) == (0, 0)


def test_projection_mismatch_is_refused_before_writing(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = store._paise

    def off_by_one(value: Any) -> int | None:
        paise = real(value)
        return None if paise is None else paise + 1

    monkeypatch.setattr(store, "_paise", off_by_one)
    with pytest.raises(store.ProjectionMismatchError):
        save_bill(db, example("matching.json"))
    assert _counts(db) == (0, 0)


def test_paise_refuses_a_non_money_value() -> None:
    value = Traced.entered(Decimal("12"), by="test", status=DataStatus.SYNTHETIC)
    with pytest.raises(TypeError, match="expected Money"):
        store._paise(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE calculation_run SET exit_code = 0",
        "UPDATE calculation_run SET calculated_total_paise = 0",
        "DELETE FROM calculation_run",
        "TRUNCATE calculation_run",
        "UPDATE bill_document SET bill_id = 'X'",
        "DELETE FROM bill_document",
        "TRUNCATE bill_document CASCADE",
    ],
)
def test_saved_records_cannot_be_changed(db: Engine, statement: str) -> None:
    saved = save_bill(db, example("differing.json"))
    before = get_run(db, saved.run_id)
    with pytest.raises((IntegrityError, InternalError), match="immutable"), db.begin() as c:
        c.execute(text(statement))
    assert get_run(db, saved.run_id) == before


VALID_RUN = {
    "command": "'reconcile'",
    "engine_version": "'t'",
    "tariff_id": "'T'",
    "tariff_name": "'T'",
    "tariff_status": "'synthetic'",
    "exit_code": "1",
    "report_format": "'samay.report/1'",
    "report_text": "'{}'",
    "report_sha256": f"'{'a' * 64}'",
    "calculated_total_paise": "100",
    "printed_total_paise": "150",
    "total_difference_paise": "50",
    "explanation": "'complete'",
}


def _insert_run(db: Engine, **changes: str) -> None:
    saved = save_bill(db, example("matching.json"))
    values = {**VALID_RUN, **changes, "bill_document_id": str(saved.bill_document_id)}
    columns = ", ".join(values)
    with db.begin() as connection:
        connection.execute(
            text(f"INSERT INTO calculation_run ({columns}) VALUES ({', '.join(values.values())})")
        )


def test_a_valid_hand_written_run_is_accepted(db: Engine) -> None:
    _insert_run(db)
    assert _counts(db) == (1, 2)


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"total_difference_paise": "49"}, "total_difference"),
        ({"total_difference_paise": "NULL"}, "total_difference"),
        ({"printed_total_paise": "NULL"}, "total_difference"),
        ({"calculated_total_paise": "NULL"}, "total_difference"),
        ({"exit_code": "2"}, "exit_code"),
        ({"command": "'calculate'"}, "exit_code"),
        ({"command": "'adjust'"}, "command"),
        ({"explanation": "NULL"}, "reconcile_fields"),
        ({"explanation": "'mostly'"}, "explanation_value"),
        ({"tariff_status": "'real'"}, "tariff_status"),
        ({"report_format": "'other/1'"}, "report_format"),
        ({"report_sha256": f"'{'A' * 64}'"}, "report_sha256"),
    ],
)
def test_check_constraints_refuse_inconsistent_runs(
    db: Engine, changes: dict[str, str], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=f"ck_calculation_run_{constraint}"):
        _insert_run(db, **changes)


def test_calculate_runs_carry_no_printed_values(db: Engine) -> None:
    with pytest.raises(IntegrityError, match="reconcile_fields"):
        _insert_run(
            db,
            command="'calculate'",
            exit_code="0",
            explanation="NULL",
            printed_total_paise="150",
            total_difference_paise="50",
        )


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("format", "'samay.bill/2'", "format"),
        ("source_sha256", "'xyz'", "source_sha256"),
        ("source_bytes", "''::bytea", "source_not_empty"),
        ("bill_id", "''", "bill_id_not_empty"),
    ],
)
def test_check_constraints_refuse_bad_documents(
    db: Engine, column: str, value: str, constraint: str
) -> None:
    values = {
        "bill_id": "'B'",
        "tariff_id": "'T'",
        "format": "'samay.bill/1'",
        "source_bytes": "'x'::bytea",
        "source_sha256": f"'{'b' * 64}'",
        column: value,
    }
    with (
        pytest.raises(IntegrityError, match=f"ck_bill_document_{constraint}"),
        db.begin() as connection,
    ):
        connection.execute(
            text(
                f"INSERT INTO bill_document ({', '.join(values)})"
                f" VALUES ({', '.join(values.values())})"
            )
        )


def test_list_is_newest_first_and_limited(db: Engine) -> None:
    ids = [save_bill(db, example(name)).run_id for name in EXAMPLE_FILES]
    runs = list_runs(db)
    assert [r.run_id for r in runs] == sorted(ids, reverse=True)
    assert [r.run_id for r in list_runs(db, limit=2)] == sorted(ids, reverse=True)[:2]
    with pytest.raises(ValueError, match="at least 1"):
        list_runs(db, limit=0)


def test_unknown_run(db: Engine) -> None:
    with pytest.raises(RunNotFoundError):
        get_run(db, 999)


def test_verify_reports_a_changed_engine_without_writing(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = save_bill(db, example("differing.json"))
    real = json_report.dumps
    monkeypatch.setattr(json_report, "dumps", lambda doc: real(doc) + " ")
    result = verify_run(db, saved.run_id)
    assert not result.matches
    assert result.stored_sha256 != result.recomputed_sha256
    assert _counts(db) == (1, 1)
