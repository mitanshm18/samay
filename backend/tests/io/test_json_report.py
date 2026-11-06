"""samay.report/1: strings only, null only for MISSING, synthetic status always present."""

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from samay.billing import recompute_bill, reconcile
from samay.core import DataStatus, Money, PowerFactor, Provenance, Traced
from samay.io import json_report as jr
from samay.io import load_bill

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bills"
NAMES = ["matching", "differing", "pass-through", "missing-data"]


def document(name: str) -> dict[str, Any]:
    loaded = load_bill((EXAMPLES / f"{name}.json").read_bytes())
    report = reconcile(loaded.bill, recompute_bill(loaded.bill, loaded.tariff))
    text = jr.dumps(jr.reconciliation_document(report, 1))
    parsed: dict[str, Any] = json.loads(text)
    return parsed


def walk(node: Any, path: str = "$") -> list[tuple[str, Any]]:
    found = [(path, node)]
    if isinstance(node, dict):
        for key, value in node.items():
            found += walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += walk(value, f"{path}[{index}]")
    return found


@pytest.mark.parametrize("name", NAMES)
def test_no_json_numbers(name: str) -> None:
    for path, value in walk(document(name)):
        assert not isinstance(value, int | float) or isinstance(value, bool), path


@pytest.mark.parametrize("name", NAMES)
def test_null_only_for_missing(name: str) -> None:
    """A null "value" sits next to provenance "missing"; other nulls are fixed keys."""
    allowed = {"banner", "rounding", "exact"}
    for path, node in walk(document(name)):
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if value is None:
                if key == "value":
                    assert node["provenance"] == "missing", path
                else:
                    assert key in allowed, f"{path}.{key}"


@pytest.mark.parametrize("name", NAMES)
def test_synthetic_status_is_everywhere(name: str) -> None:
    doc = document(name)
    assert doc["format"] == "samay.report/1"
    assert doc["synthetic"] is True
    assert "SYNTHETIC" in doc["banner"]
    assert doc["tariff"] == {
        "id": "SAMAY-DEMO-1",
        "name": doc["tariff"]["name"],
        "status": "synthetic",
    }
    assert any(w["code"] == "synthetic-tariff" for w in doc["warnings"])
    for path, node in walk(doc):
        if isinstance(node, dict) and "status" in node and "provenance" in node:
            assert node["status"] == "synthetic", path


def test_estimates_are_named() -> None:
    doc = document("pass-through")
    duty = next(
        line for line in doc["reconciliation"]["lines"] if line["code"] == "electricity_duty"
    )
    assert duty["printed"]["provenance"] == "estimated"
    assert duty["rests_on_estimate"] is True
    assert duty["estimate_bases"]
    assert any(w["code"] == "input-estimated" for w in doc["warnings"])
    assert doc["reconciliation"]["rests_on_estimate"] is True


def test_money_has_rupees_and_paise() -> None:
    doc = document("differing")
    energy = next(
        line for line in doc["reconciliation"]["lines"] if line["code"] == "energy_charge"
    )
    assert energy["status"] == "DIFFERS"
    assert energy["difference"]["value"] == "0.01"
    assert energy["difference"]["paise"] == "1"
    assert energy["difference"]["unit"] == "INR"
    assert doc["reconciliation"]["explanation"]["state"] == "COMPLETE"
    assert doc["exit_code"] == "1"


def test_missing_values_carry_reasons() -> None:
    doc = document("missing-data")
    total = doc["reconciliation"]["total"]
    assert total["difference"]["value"] is None
    assert total["difference"]["missing_reasons"]
    assert doc["calculation"]["complete"] is False


def test_render_value() -> None:
    assert jr.render_value(Money(-5)) == {"value": "-0.05", "unit": "INR", "paise": "-5"}
    assert jr.render_value(Decimal("1E+3")) == {"value": "1000"}
    pf = jr.render_value(PowerFactor(Fraction(2, 3)))
    assert pf["value"] == "2/3"
    assert pf["rounded_3_places_half_up"] == "0.667"
    with pytest.raises(TypeError):
        jr.render_value(1.5)


def test_leaves_of_a_derived_value() -> None:
    v = DataStatus.VERIFIED
    a = Traced.entered(Money(100), by="a", status=v)
    b = Traced.estimated(Money(5), basis="b guessed", status=v)
    total = Traced.derive(lambda x, y: x + y, a, b, description="a + b")
    data = jr.traced(total)
    assert data["provenance"] == "calculated"
    assert data["status"] == "verified"
    assert [leaf["note"] for leaf in data["leaves"]] == ["a", "b guessed"]
    assert data["estimate_bases"] == ["b guessed"]
    assert "leaves" not in jr.traced(a)
    gone = Traced.missing(reason="gone", status=v, kind=Money)
    missing = jr.traced(gone)
    assert missing["value"] is None
    assert missing["provenance"] == Provenance.MISSING.value
    assert missing["missing_reasons"] == ["gone"]
    derived = jr.traced(Traced.derive(lambda x: x, gone, description="copy"))
    assert derived["leaves"][0]["value"] is None
    assert derived["missing_reasons"] == ["gone"]


def test_output_is_deterministic() -> None:
    assert document("matching") == document("matching")
    assert jr.internal_error_document("calculate", "boom") == {
        "format": "samay.report/1",
        "command": "calculate",
        "exit_code": "3",
        "internal_error": "boom",
    }


def test_reconciliation_without_a_printed_total() -> None:
    data = json.loads((EXAMPLES / "matching.json").read_text("utf-8"))
    del data["printed"]["total_rupees"]
    loaded = load_bill(json.dumps(data).encode())
    report = reconcile(loaded.bill, recompute_bill(loaded.bill, loaded.tariff))
    total = jr.reconciliation(report)["total"]
    assert total["printed_total_given"] is False
    assert "printed" not in total
    assert total["difference"]["value"] is None
    assert total["difference"]["note"] == "no printed total was given"
