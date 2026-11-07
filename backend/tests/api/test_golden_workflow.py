"""Step 7: the three hand-checked golden bills through the whole demo workflow.

The demo files examples/bills/golden-gb*.json are the golden inputs with the printed
variant built from the CHECKER'S values (tests/golden/test_golden.py), so the demo
shows bills whose every figure was worked out by hand, not by SAMAY.

Each bill goes through what the web page does: validate, calculate-and-reconcile and
save, history, run detail, the exact report, the exact source, verify, and a
calculate-only run. Every line and total is compared with the hand-check, to the paisa.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from dbhelpers import EXAMPLES, GOLDEN
from samay.api import create_app

BILLS = ("GB1", "GB2", "GB3")


def _golden() -> ModuleType:
    spec = importlib.util.spec_from_file_location("golden_workflow", GOLDEN / "test_golden.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


golden = _golden()


def demo_file(bill_id: str) -> bytes:
    return (EXAMPLES / f"golden-{bill_id.lower()}.json").read_bytes()


@pytest.fixture
def client(db: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(db), raise_server_exceptions=False) as test_client:
        yield test_client


def paise(node: dict[str, Any] | None) -> str:
    """A money value as the hand-check writes it: digits, or MISSING."""
    if node is None or node.get("value") is None:
        return str(golden.MISSING)
    return str(node["paise"])


def money(node: dict[str, str] | None, absent: str) -> str:
    """A summary amount ({"paise", "inr"} or null) as the hand-check writes it."""
    return absent if node is None else node["paise"]


def difference(node: dict[str, Any] | None) -> str:
    if node is None or node.get("value") is None:
        return str(golden.UNDETERMINED)
    return str(node["paise"])


@pytest.mark.parametrize("bill_id", BILLS)
def test_demo_file_is_the_hand_checked_bill(bill_id: str) -> None:
    """The demo file is exactly the golden input plus the checker's printed variant."""
    want = golden.input_json(bill_id)
    want["printed"] = golden.printed_variant(bill_id, golden.signed(bill_id)["calculation"])
    assert json.loads(demo_file(bill_id)) == want


@pytest.mark.parametrize("bill_id", BILLS)
def test_golden_bill_through_the_whole_workflow(client: TestClient, bill_id: str) -> None:
    signed = golden.signed(bill_id)
    calc, recon = signed["calculation"], signed["reconciliation"]
    data = demo_file(bill_id)

    # 1. Validate: valid, synthetic, nothing saved.
    validation = client.post("/api/validate", content=data)
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert validation.json()["synthetic"] is True
    assert client.get("/api/runs").json() == {"runs": []}

    # 2. Calculate, reconcile and save.
    created = client.post("/api/runs", params={"command": "reconcile"}, content=data)
    assert created.status_code == 201
    run_id = created.json()["run"]["run_id"]

    # 3. History lists it.
    history = client.get("/api/runs").json()["runs"]
    assert [r["run_id"] for r in history] == [run_id]
    summary = history[0]
    assert summary["bill_id"] == bill_id
    assert summary["synthetic"] is True
    assert summary["outcome"] == ("clean" if recon["exit_code"] == "0" else "not-clean")

    # 4. The run detail: every line and total against the hand-check, to the paisa.
    detail = client.get(f"/api/runs/{run_id}").json()
    report = detail["report"]
    assert report["synthetic"] is True
    lines = {line["code"]: line for line in report["calculation"]["lines"]}
    assert {code: paise(lines[code]["amount"]) for code in calc["lines_paise"]} == calc[
        "lines_paise"
    ]
    assert paise(report["calculation"]["subtotal"]) == calc["subtotal_paise"]
    assert paise(report["calculation"]["total"]) == calc["total_paise"]
    rec = report["reconciliation"]
    got = {
        line["code"]: {"status": line["status"], "difference_paise": difference(line["difference"])}
        for line in rec["lines"]
    }
    want = {
        code: {"status": item["status"], "difference_paise": item["difference_paise"]}
        for code, item in recon["lines"].items()
    }
    assert got == want
    assert paise(rec["total"]["printed"]) == recon["printed_total_paise"]
    assert paise(rec["total"]["calculated"]) == recon["calculated_total_paise"]
    assert difference(rec["total"]["difference"]) == recon["total_difference_paise"]
    assert rec["explanation"]["state"] == recon["explanation"]
    assert report["exit_code"] == recon["exit_code"]
    # The summary columns agree with the report.
    totals = detail["run"]["totals"]
    assert money(totals["calculated"], golden.MISSING) == recon["calculated_total_paise"]
    assert money(totals["printed"], golden.MISSING) == recon["printed_total_paise"]
    assert money(totals["difference"], golden.UNDETERMINED) == recon["total_difference_paise"]
    # Missing is never zero: a MISSING total has no amount at all.
    if recon["calculated_total_paise"] == golden.MISSING:
        assert totals["calculated"] is None
        assert totals["difference"] is None

    # 5. The exact report and the exact bill file.
    report_response = client.get(f"/api/runs/{run_id}/report")
    assert report_response.status_code == 200
    assert json.loads(report_response.content) == report
    source = client.get(f"/api/runs/{run_id}/source")
    assert source.content == data

    # 6. Verify: recalculated from the saved bill, identical report.
    verify = client.post(f"/api/runs/{run_id}/verify").json()
    assert verify["matches"] is True

    # 7. Calculate only: the same total, no printed bill compared.
    calc_run = client.post("/api/runs", params={"command": "calculate"}, content=data)
    assert calc_run.status_code == 201
    calc_summary = calc_run.json()["run"]
    assert calc_summary["outcome"] == "calculated"
    assert money(calc_summary["totals"]["calculated"], golden.MISSING) == calc["total_paise"]
    assert calc_summary["totals"]["printed"] is None
    history = client.get("/api/runs").json()["runs"]
    assert [r["run_id"] for r in history] == [calc_summary["run_id"], run_id]
