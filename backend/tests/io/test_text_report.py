"""Plain-text reports: banner first, missing values named, estimates listed."""

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from samay import cli
from samay.billing import recompute_bill, reconcile
from samay.core import ApparentEnergy, DataStatus, Traced
from samay.io import load_bill, text_report
from samay.tariffs import SAMAY_DEMO_1, Tariff

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bills"


def test_no_banner_and_no_warnings_for_a_verified_tariff() -> None:
    # A real verified tariff needs a source per component; none exists yet (D8).
    verified = cast(Tariff, SimpleNamespace(is_synthetic=False))
    assert cli._banner(verified) is None
    assert cli._banner(SAMAY_DEMO_1) is not None
    text = text_report.validation_text("B-1", None, ())
    assert text == "Bill B-1: valid.\n"


def test_calculation_lists_estimates() -> None:
    loaded = load_bill((EXAMPLES / "matching.json").read_bytes())
    bill = dataclasses.replace(
        loaded.bill,
        kvah=Traced.estimated(
            ApparentEnergy("100000"), basis="kVAh from last month", status=DataStatus.SYNTHETIC
        ),
    )
    text = text_report.calculation_text(recompute_bill(bill, loaded.tariff))
    assert "Rests on estimates: kVAh from last month" in text


def test_explanation_reasons() -> None:
    data = json.loads((EXAMPLES / "missing-data.json").read_text("utf-8"))
    loaded = load_bill(json.dumps(data).encode())
    report = reconcile(loaded.bill, recompute_bill(loaded.bill, loaded.tariff))
    reasons = report.explanation.reasons
    assert reasons
    assert all(": " in reason for reason in reasons)
    assert len(reasons) == len(report.explanation.not_compared)
