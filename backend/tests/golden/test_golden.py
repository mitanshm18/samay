"""Golden bills: SAMAY against values worked out by hand by an independent checker.

The expected values in expected/GBn.json come ONLY from the signed hand-check
worksheets (decision 0004, D8). Nobody may fill them in by running SAMAY.

Until all three files are filled in and signed, test_golden_bills_are_signed_off
fails on purpose: Step 3B must not merge before the hand-check (decision 0003).
The comparison tests skip until then, so they never pass against blank values.

Each bill is checked twice:
1. calculation: every line, the other lines, subtotal and total, to the paisa;
2. reconciliation: a printed bill is built from the CHECKER'S values (not SAMAY's)
   with the deliberate changes below, and SAMAY's reconciliation is compared with
   the checker's expected statuses and differences.

Printed variants (the changes are fixed here and in the worksheet, Part 2):
  GB1  every line as the checker worked it out, except the excess demand line,
       which is left off the printed bill. Printed total = checker's total.
  GB2  every line as worked out, but the energy charge printed 1 paisa higher;
       meter rent Rs 1,250.00 printed as an 'other' line. Printed total =
       checker's total (so the printed lines no longer add up to it).
  GB3  demand, excess demand and energy as worked out; the ToD line is on the
       bill but illegible (MISSING); duty and rounding off are not printed;
       meter rent Rs 1,250.00 as an 'other' line; printed total Rs 4,50,000.00.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from samay import cli
from samay.billing import LineStatus, MoneyLine, recompute_bill, reconcile
from samay.core import Money, Traced
from samay.io import load_bill
from samay.tariffs import ComponentCode

HERE = Path(__file__).resolve().parent
BILLS = ("GB1", "GB2", "GB3")
CODES = tuple(c.value for c in ComponentCode if c is not ComponentCode.OTHER)
MISSING = "MISSING"
UNDETERMINED = "NOT DETERMINABLE"
METER_RENT = 125_000  # paise; given on the worksheet, not calculated
GB3_PRINTED_TOTAL = 45_000_000  # paise; Rs 4,50,000.00, fixed by the worksheet

_PAISE = re.compile(r"-?(0|[1-9][0-9]*)")
_KVA = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?")


def expected(bill_id: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((HERE / "expected" / f"{bill_id}.json").read_text("utf-8"))
    return data


def input_json(bill_id: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((HERE / "inputs" / f"{bill_id}.json").read_text("utf-8"))
    return data


def blanks(node: Any, path: str = "$") -> list[str]:
    """Paths of every value still left blank (null or empty)."""
    if isinstance(node, dict):
        return [p for key, value in node.items() for p in blanks(value, f"{path}.{key}")]
    return [path] if node is None or node == "" else []


def unsigned(bill_id: str) -> list[str]:
    return blanks(expected(bill_id))


# ---- the merge gate -----------------------------------------------------------------


def test_golden_bills_are_signed_off() -> None:
    """Fails until the checker has filled in and signed all three worksheets."""
    waiting = {bill_id: unsigned(bill_id) for bill_id in BILLS}
    waiting = {bill_id: paths for bill_id, paths in waiting.items() if paths}
    assert not waiting, (
        "Golden bills not yet hand-checked and signed off (Step 3B merge gate). "
        "Blank values: "
        + "; ".join(
            f"{bill_id}: {len(paths)} blank, e.g. {paths[0]}" for bill_id, paths in waiting.items()
        )
    )


@pytest.mark.parametrize("bill_id", BILLS)
def test_expected_files_have_the_agreed_shape(bill_id: str) -> None:
    """The template itself: right keys, and any value filled in is well formed."""
    data = expected(bill_id)
    assert set(data) == {"bill_id", "checked_by", "checked_on", "calculation", "reconciliation"}
    assert data["bill_id"] == bill_id
    calc = data["calculation"]
    assert set(calc) == {
        "billing_demand_kva",
        "lines_paise",
        "other_lines_paise",
        "subtotal_paise",
        "total_paise",
    }
    assert tuple(calc["lines_paise"]) == CODES
    recon = data["reconciliation"]
    assert set(recon) == {
        "lines",
        "total_difference_paise",
        "printed_lines_residual_paise",
        "explanation",
        "exit_code",
    }
    line_codes = CODES if bill_id == "GB1" else (*CODES, "other")
    assert tuple(recon["lines"]) == line_codes
    for value in [data["checked_by"], data["checked_on"], calc["billing_demand_kva"]]:
        assert value is None or isinstance(value, str)
    if data["checked_on"] is not None:
        date.fromisoformat(data["checked_on"])
    if calc["billing_demand_kva"] is not None:
        assert _KVA.fullmatch(calc["billing_demand_kva"])
    amounts = [*calc["lines_paise"].values(), calc["other_lines_paise"]]
    amounts += [calc["subtotal_paise"], calc["total_paise"]]
    for value in amounts:
        assert value is None or value == MISSING or _PAISE.fullmatch(value), value
    statuses = {s.name for s in LineStatus}
    for item in recon["lines"].values():
        assert set(item) == {"status", "difference_paise"}
        assert item["status"] is None or item["status"] in statuses, item
        assert _difference_ok(item["difference_paise"]), item
    assert _difference_ok(recon["total_difference_paise"])
    assert _difference_ok(recon["printed_lines_residual_paise"])
    assert recon["explanation"] in (None, "COMPLETE", "PARTIAL", "UNDETERMINABLE")
    assert recon["exit_code"] in (None, "0", "1")


def _difference_ok(value: object) -> bool:
    return (
        value is None
        or value == UNDETERMINED
        or (isinstance(value, str) and _PAISE.fullmatch(value) is not None)
    )


@pytest.mark.parametrize("bill_id", BILLS)
def test_golden_inputs_are_valid(bill_id: str) -> None:
    """Only validation runs on the inputs before sign-off; nothing is calculated."""
    loaded = load_bill((HERE / "inputs" / f"{bill_id}.json").read_bytes())
    assert loaded.bill.bill_id == bill_id
    assert loaded.bill.printed_lines == ()


# ---- comparisons (run only after sign-off) --------------------------------------------


def signed(bill_id: str) -> dict[str, Any]:
    if unsigned(bill_id):
        pytest.skip(f"{bill_id} is not signed off yet; see test_golden_bills_are_signed_off")
    return expected(bill_id)


def show(value: Traced[Money]) -> str:
    return MISSING if value.is_missing else str(value.value.paise)


def show_difference(value: Traced[Money]) -> str:
    return UNDETERMINED if value.is_missing else str(value.value.paise)


def rupees(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    whole, part = divmod(abs(paise), 100)
    return f"{sign}{whole}.{part:02d}"


def printed_amount(paise_text: str, note: str) -> dict[str, str]:
    if paise_text == MISSING:
        return {"provenance": "missing", "note": f"{note}: not worked out by the checker"}
    return {"value": rupees(int(paise_text)), "provenance": "entered", "note": note}


def printed_variant(bill_id: str, calc: dict[str, Any]) -> dict[str, Any]:
    """The printed bill for Part 2, built from the checker's own values."""
    worked = calc["lines_paise"]
    note = f"golden bill {bill_id[-1]} printed variant"

    def line(code: str, label: str, amount: dict[str, str]) -> dict[str, Any]:
        return {"code": code, "label": label, "amount_rupees": amount}

    def as_worked(code: str) -> dict[str, Any]:
        return line(code, code.replace("_", " "), printed_amount(worked[code], f"{note}, {code}"))

    rent = line("other", "Meter rent", printed_amount(str(METER_RENT), f"{note}, meter rent"))
    total = printed_amount(calc["total_paise"], f"{note}, total")
    if bill_id == "GB1":
        lines = [as_worked(c) for c in CODES if c != "excess_demand_charge"]
    elif bill_id == "GB2":
        lines = [as_worked(c) for c in CODES]
        energy = int(worked["energy_charge"]) + 1  # the deliberate 1 paisa error
        lines[CODES.index("energy_charge")]["amount_rupees"] = printed_amount(
            str(energy), f"{note}, energy charge printed 1 paisa high"
        )
        lines.append(rent)
    else:
        lines = [as_worked(c) for c in ("demand_charge", "excess_demand_charge", "energy_charge")]
        lines.append(
            line(
                "tod_adjustment",
                "ToD adjustment",
                {"provenance": "missing", "note": f"{note}: ToD figure illegible"},
            )
        )
        lines.append(rent)
        total = printed_amount(str(GB3_PRINTED_TOTAL), f"{note}, total")
    return {"lines": lines, "total_rupees": total}


@pytest.mark.parametrize("bill_id", BILLS)
def test_calculation_matches_the_hand_check(bill_id: str) -> None:
    calc = signed(bill_id)["calculation"]
    data = input_json(bill_id)
    data["printed"] = printed_variant(bill_id, calc)
    loaded = load_bill(json.dumps(data).encode("utf-8"))
    result = recompute_bill(loaded.bill, loaded.tariff)
    demand = next(q for q in result.quantities if q.key == "billing_demand")
    assert Decimal(calc["billing_demand_kva"]) == demand.value.value.value
    by_code: dict[str, MoneyLine] = {
        line.code.value: line for line in result.lines if line.code is not ComponentCode.OTHER
    }
    got = {code: show(by_code[code].amount) for code in CODES}
    assert got == calc["lines_paise"]
    other = sum(line.amount.value.paise for line in result.not_recalculated_lines)
    assert str(other) == calc["other_lines_paise"]
    assert show(result.subtotal) == calc["subtotal_paise"]
    assert show(result.total) == calc["total_paise"]


@pytest.mark.parametrize("bill_id", BILLS)
def test_reconciliation_matches_the_hand_check(bill_id: str) -> None:
    data_expected = signed(bill_id)
    calc, recon = data_expected["calculation"], data_expected["reconciliation"]
    data = input_json(bill_id)
    data["printed"] = printed_variant(bill_id, calc)
    loaded = load_bill(json.dumps(data).encode("utf-8"))
    report = reconcile(loaded.bill, recompute_bill(loaded.bill, loaded.tariff))
    got = {
        line.code.value: {
            "status": line.status.name,
            "difference_paise": show_difference(line.difference),
        }
        for line in report.lines
    }
    assert got == recon["lines"]
    assert show_difference(report.total.difference) == recon["total_difference_paise"]
    assert show_difference(report.total.residual) == recon["printed_lines_residual_paise"]
    assert report.explanation.state.name == recon["explanation"]
    assert str(cli.reconcile_exit_code(report)) == recon["exit_code"]
    assert report.tariff_status.value == "synthetic"
