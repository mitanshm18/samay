"""samay.optimise: explainable cost-reduction opportunities.

Every saving must equal current total - scenario total as recalculated by the bill
engine itself; nothing is invented when data is missing; a synthetic tariff only
ever gives an ILLUSTRATIVE saving.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from samay.billing import recompute_bill
from samay.core import ApparentEnergy, ApparentPower, DataStatus, Money, Rate, Traced, Unit
from samay.io import load_bill
from samay.optimise import (
    Confidence,
    Kind,
    OptimisationReport,
    Recommendation,
    Saving,
    SavingStatus,
    optimisation_document,
    optimise,
)
from samay.optimise import document as document_module
from samay.tariffs import TodRate
from samay.tariffs.model import SourceRef

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bills"


def bill_json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / name).read_text("utf-8"))
    return data


def run(data: dict[str, Any]) -> OptimisationReport:
    loaded = load_bill(json.dumps(data).encode("utf-8"))
    return optimise(loaded.bill, loaded.tariff)


def example(name: str) -> OptimisationReport:
    return run(bill_json(name))


def rec(report: OptimisationReport, key: str) -> Recommendation:
    found = [r for r in report.recommendations if r.key == key]
    assert len(found) == 1, [r.key for r in report.recommendations]
    return found[0]


def keys(report: OptimisationReport) -> list[str]:
    return [r.key for r in report.recommendations]


def set_reading(data: dict[str, Any], key: str, value: str | None) -> dict[str, Any]:
    data = copy.deepcopy(data)
    if value is None:
        data["readings"][key] = {"provenance": "missing", "note": f"test: {key} not printed"}
    else:
        data["readings"][key]["value"] = value
    return data


def paise(money: Money | None) -> int | None:
    return None if money is None else money.paise


# ---- every saving is the bill engine's own difference ------------------------------


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.json")))
def test_every_saving_is_current_minus_scenario_from_the_engine(name: str) -> None:
    loaded = load_bill((EXAMPLES / name).read_bytes())
    report = optimise(loaded.bill, loaded.tariff)
    current = recompute_bill(loaded.bill, loaded.tariff).total
    assert paise(report.current_total) == (None if current.is_missing else current.value.paise)
    for item in report.recommendations:
        saving = item.saving
        if saving.amount is not None:
            assert saving.current_total == report.current_total
            assert saving.scenario_total is not None
            assert saving.current_total is not None
            assert saving.amount.paise == saving.current_total.paise - saving.scenario_total.paise
            assert saving.amount.paise > 0
            # synthetic tariff: never presented as a real saving
            assert saving.status is SavingStatus.ILLUSTRATIVE
            assert "not a real-world saving" in saving.note
        else:
            assert saving.status is not SavingStatus.ILLUSTRATIVE
            assert saving.status is not SavingStatus.ESTIMATED
    assert report.synthetic
    assert report.banner is not None


def test_excess_demand_on_golden_bill_2() -> None:
    report = example("golden-gb2.json")
    item = rec(report, "excess-demand")
    assert item.kind is Kind.ACTIONABLE
    assert item.confidence is Confidence.HIGH
    assert "337.125 kVA exceeded the contract demand of 300.000 kVA by 37.125 kVA" in item.finding
    # Hand check: demand 400 x 37.125 = 14,850.00; excess 1.5 x 400 x 37.125 = 22,275.00;
    # duty 5% of 37,125.00 = 1,856.25; 38,981.25 less, then rounded to the rupee.
    assert paise(item.saving.amount) == 3_898_100
    assert report.recommendations[0].kind is Kind.ACTIONABLE
    assert "peak-shaving" not in keys(report)


def test_peak_shaving_power_factor_and_load_shift_on_a_complete_bill() -> None:
    report = example("matching.json")
    shave = rec(report, "peak-shaving")
    assert shave.kind is Kind.INDICATIVE
    assert shave.saving.scenario == "maximum demand reduced to 375.000 kVA"  # floor wins
    assert shave.assumptions
    pf = rec(report, "power-factor")
    assert pf.kind is Kind.ACTIONABLE
    assert "0.900" in pf.finding
    assert pf.saving.scenario == "power factor 0.99 (90909.091 kVAh)"
    shift = rec(report, "load-shift")
    assert shift.kind is Kind.INDICATIVE
    assert shift.saving.scenario == "2500.000 kVAh moved from peak to off-peak"
    # 2,500 kVAh x (150 + 100) paise = 6,250.00, plus 5% duty = 6,562.50, then rounding
    assert paise(shift.saving.amount) == 656_300
    assert rec(report, "load-factor").kind is Kind.INDICATIVE  # 33.7%: peaky
    assert rec(report, "trend").kind is Kind.INSUFFICIENT_DATA


def test_missing_total_gives_insufficient_data_never_an_estimate() -> None:
    report = example("golden-gb3.json")
    assert report.current_total is None
    for item in report.recommendations:
        assert item.saving.amount is None
    pf = rec(report, "power-factor")
    assert pf.saving.status is SavingStatus.INSUFFICIENT_DATA
    assert "current bill total cannot be calculated" in pf.saving.note
    shift = rec(report, "load-shift")
    assert shift.kind is Kind.INSUFFICIENT_DATA
    assert any("off_peak zone" in m for m in shift.missing_data)


def test_no_zone_readings() -> None:
    data = bill_json("matching.json")
    del data["readings"]["tod_kvah"]
    shift = rec(run(data), "load-shift")
    assert shift.kind is Kind.INSUFFICIENT_DATA
    assert shift.missing_data == ("no time-of-day zone readings on the bill",)


def test_missing_demand_values() -> None:
    report = run(set_reading(bill_json("matching.json"), "recorded_md_kva", None))
    item = rec(report, "demand-insufficient")
    assert item.kind is Kind.INSUFFICIENT_DATA
    assert item.missing_data[0].startswith("recorded maximum demand: test: recorded_md_kva")
    assert report.profile.load_factor_percent is None
    assert "load-factor" not in keys(report)


def test_missing_kwh_gives_no_power_factor() -> None:
    report = run(set_reading(bill_json("matching.json"), "kwh", None))
    item = rec(report, "power-factor")
    assert item.kind is Kind.INSUFFICIENT_DATA
    assert item.missing_data == ("kWh: test: kwh not printed",)
    assert report.profile.power_factor is None


def test_healthy_power_factor() -> None:
    report = run(set_reading(bill_json("matching.json"), "kwh", "97000.000"))
    item = rec(report, "power-factor")
    assert item.kind is Kind.INFORMATION
    assert item.saving.status is SavingStatus.NOT_APPLICABLE
    assert "0.970" in item.finding


def test_oversized_contract_demand() -> None:
    data = set_reading(bill_json("matching.json"), "recorded_md_kva", "300.000")
    item = rec(run(data), "contract-demand")
    assert item.kind is Kind.INDICATIVE
    # 300 kVA x 1.1 margin / 0.75 floor = 440 kVA
    assert item.saving.scenario == "contract demand 440 kVA"
    assert item.saving.amount is not None
    assert item.saving.amount.paise > 0
    assert "peak-shaving" not in keys(run(data))


def test_no_contract_change_when_the_margin_needs_more_than_contract() -> None:
    data = set_reading(bill_json("matching.json"), "recorded_md_kva", "370.000")
    report = run(data)
    assert "contract-demand" not in keys(report)
    assert "peak-shaving" not in keys(report)  # below the floor: shaving saves nothing


def test_steady_load_and_odd_period_length() -> None:
    data = set_reading(bill_json("matching.json"), "recorded_md_kva", "150.000")
    data["period"]["end"] = "2026-05-01T00:30:00+05:30"
    report = run(data)
    assert rec(report, "load-factor").kind is Kind.INFORMATION
    assert report.profile.period_hours == "720.50"


def test_no_peak_energy() -> None:
    data = copy.deepcopy(bill_json("matching.json"))
    zones = data["readings"]["tod_kvah"]
    zones["normal"]["value"] = "70000.000"
    zones["peak"]["value"] = "0.000"
    item = rec(run(data), "load-shift")
    assert item.kind is Kind.INFORMATION
    assert item.finding == "No energy was used in the peak zone."


def test_flat_time_of_day_rates_give_nothing_to_shift() -> None:
    loaded = load_bill((EXAMPLES / "matching.json").read_bytes())
    flat = tuple(
        TodRate(t.zone, t.hours, Rate.rupees_per("0", Unit.KVAH)) for t in loaded.tariff.tod_rates
    )
    report = optimise(loaded.bill, dataclasses.replace(loaded.tariff, tod_rates=flat))
    item = rec(report, "load-shift")
    assert item.kind is Kind.INFORMATION
    assert "does not charge more in peak hours" in item.finding


def verified(tariff: Any) -> Any:
    source = SourceRef("test order", "p. 1")
    terms = tuple(dataclasses.replace(t, source=source) for t in tariff.components)
    return dataclasses.replace(tariff, status=DataStatus.VERIFIED, components=terms)


def test_verified_tariff_and_readings_give_an_estimated_saving() -> None:
    data = bill_json("golden-gb2.json")
    data["data_status"] = "verified"
    loaded = load_bill(json.dumps(data).encode("utf-8"))
    item = rec(optimise(loaded.bill, verified(loaded.tariff)), "excess-demand")
    assert item.saving.status is SavingStatus.ESTIMATED
    assert paise(item.saving.amount) == 3_898_100


def test_synthetic_readings_stay_illustrative_with_a_verified_tariff() -> None:
    loaded = load_bill((EXAMPLES / "golden-gb2.json").read_bytes())
    item = rec(optimise(loaded.bill, verified(loaded.tariff)), "excess-demand")
    assert item.saving.status is SavingStatus.ILLUSTRATIVE
    assert "readings are marked SYNTHETIC" in item.saving.note


def test_estimated_inputs_lower_confidence() -> None:
    data = copy.deepcopy(bill_json("golden-gb2.json"))
    data["readings"]["recorded_md_kva"]["provenance"] = "estimated"
    item = rec(run(data), "excess-demand")
    assert item.confidence is Confidence.MEDIUM
    assert "estimated input" in item.confidence_reason


def test_a_bill_that_cannot_be_recalculated() -> None:
    loaded = load_bill((EXAMPLES / "matching.json").read_bytes())
    zones = loaded.bill.zones
    assert zones is not None
    broken = dataclasses.replace(
        zones,
        peak=Traced.entered(ApparentEnergy("1.000"), by="test", status=DataStatus.SYNTHETIC),
    )  # zones no longer add up to total kVAh: validation error
    report = optimise(dataclasses.replace(loaded.bill, zones=broken), loaded.tariff)
    assert report.current_total is None
    assert report.banner is None
    assert report.profile.billing_demand_kva is None
    item = rec(report, "power-factor")
    assert "the bill could not be recalculated" in item.saving.note


def test_scenario_that_cannot_be_calculated(monkeypatch: pytest.MonkeyPatch) -> None:
    import samay.optimise.engine as engine

    loaded = load_bill((EXAMPLES / "golden-gb2.json").read_bytes())
    real = engine._total
    calls: list[int] = []

    def first_only(bill: Any, tariff: Any) -> Any:
        calls.append(1)
        return real(bill, tariff) if len(calls) == 1 else None

    monkeypatch.setattr(engine, "_total", first_only)
    item = rec(optimise(loaded.bill, loaded.tariff), "excess-demand")
    assert item.saving.status is SavingStatus.INSUFFICIENT_DATA
    assert item.saving.note == "Insufficient data: the scenario bill cannot be calculated."


def test_zero_energy() -> None:
    data = set_reading(bill_json("matching.json"), "kvah", "0.000")
    data = set_reading(data, "kwh", "0.000")
    del data["readings"]["tod_kvah"]
    report = run(data)
    assert rec(report, "power-factor").kind is Kind.INSUFFICIENT_DATA
    assert rec(report, "power-factor").missing_data == ("kWh: zero", "kVAh: zero")
    assert all(z.percent is None for z in report.profile.zones)


def test_input_types_are_checked() -> None:
    loaded = load_bill((EXAMPLES / "matching.json").read_bytes())
    with pytest.raises(TypeError):
        optimise("bill", loaded.tariff)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        optimise(loaded.bill, "tariff")  # type: ignore[arg-type]


def test_other_charges_are_flagged_for_review() -> None:
    item = rec(example("golden-gb2.json"), "other-charges")
    assert item.kind is Kind.INFORMATION
    assert "Meter rent ₹1,250.00" in item.finding
    assert item.saving.status is SavingStatus.INSUFFICIENT_DATA


def test_missing_other_charge_is_shown_as_missing() -> None:
    data = copy.deepcopy(bill_json("golden-gb2.json"))
    for line in data["printed"]["lines"]:
        if line["code"] == "other":
            line["amount_rupees"] = {"provenance": "missing", "note": "test: illegible"}
    assert "Meter rent MISSING" in rec(run(data), "other-charges").finding


# ---- the JSON document ---------------------------------------------------------------


def no_numbers(value: object) -> bool:
    if isinstance(value, dict):
        return all(no_numbers(v) for v in value.values())
    if isinstance(value, list):
        return all(no_numbers(v) for v in value)
    return isinstance(value, str | bool) or value is None


@pytest.mark.parametrize("name", ["golden-gb2.json", "golden-gb3.json", "missing-data.json"])
def test_document_has_no_json_numbers_and_missing_is_null(name: str) -> None:
    document = optimisation_document(example(name))
    assert no_numbers(document)
    assert document["format"] == "samay.optimisation/1"
    assert document["synthetic"] is True
    assert sum(int(v) for v in document["counts"].values()) == len(document["recommendations"])
    if name != "golden-gb2.json":
        assert document["current_total"] is None
        assert all(r["saving"]["amount"] is None for r in document["recommendations"])


def test_document_profile_for_charts() -> None:
    document = optimisation_document(example("golden-gb3.json"))
    zones = {z["zone"]: z for z in document["profile"]["zones"]}
    assert zones["off_peak"]["kvah"] is None
    assert zones["off_peak"]["percent"] is None
    assert zones["peak"]["kvah"] is not None
    assert document["profile"]["contract_demand_kva"] == "400.000"
    _ = ApparentPower  # imported for readability of the hand checks above


def test_high_peak_share_and_missing_total_kvah() -> None:
    data = copy.deepcopy(bill_json("matching.json"))
    zones = data["readings"]["tod_kvah"]
    zones["peak"]["value"] = "40000.000"
    zones["normal"]["value"] = "30000.000"
    item = rec(run(data), "load-shift")
    assert item.title == "High peak-hour consumption: shift flexible load"
    assert "(40.0% of the month)" in item.finding
    item = rec(run(set_reading(data, "kvah", None)), "load-shift")
    assert item.title == "Shift flexible load out of peak hours"
    assert "of the month" not in item.finding


def test_saving_share_of_bill_is_exact_text() -> None:
    document = optimisation_document(example("golden-gb2.json"))
    shares = {r["key"]: r["saving"]["share_of_bill"] for r in document["recommendations"]}
    # 3,898,100 / 88,758,100 paise = 4.39...% -> 4.4%
    assert shares["excess-demand"] == "4.4%"
    assert shares["trend"] is None
    gb3 = optimisation_document(example("golden-gb3.json"))
    assert all(r["saving"]["share_of_bill"] is None for r in gb3["recommendations"])


@pytest.mark.parametrize(
    ("current", "scenario", "share"),
    [(10_000, 10_050, "-0.5%"), (0, 0, None), (1_000, 995, "0.5%"), (1_000, 996, "0.4%")],
)
def test_share_of_bill_rounding_and_edges(current: int, scenario: int, share: str | None) -> None:
    saving = Saving(SavingStatus.ILLUSTRATIVE, "note", Money(current), Money(scenario), "s")
    assert document_module._share_of_bill(saving) == share
