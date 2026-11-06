"""Tariff definitions: SAMAY-DEMO-1's numbers and the validation rules."""

import dataclasses
from decimal import Decimal
from typing import Any

import pytest

from samay.core import DataStatus, Rate, RateBasis, RoundingRule, Unit
from samay.tariffs import (
    CALCULATED_CODES,
    SAMAY_DEMO_1,
    Assumption,
    ComponentCode,
    ComponentTerms,
    SourceRef,
    Tariff,
    TariffError,
    TodRate,
    TodZone,
    get_tariff,
)

T = SAMAY_DEMO_1


def test_demo_tariff_numbers() -> None:
    assert T.tariff_id == "SAMAY-DEMO-1"
    assert T.status is DataStatus.SYNTHETIC
    assert T.is_synthetic
    assert T.demand_rate.paise_per_unit == Decimal(40000)
    assert T.demand_rate.basis is RateBasis.PER_UNIT_PER_BILLING_PERIOD
    assert T.demand_floor_percent == Decimal(75)
    assert T.excess_demand_multiplier == Decimal("1.5")
    assert T.energy_rate.paise_per_unit == Decimal(900)
    assert T.tod_rate(TodZone.PEAK).paise_per_unit == Decimal(150)
    assert T.tod_rate(TodZone.OFF_PEAK).paise_per_unit == Decimal(-100)
    assert T.tod_rate(TodZone.NORMAL).paise_per_unit == Decimal(0)
    assert T.duty_percent == Decimal(5)
    assert T.line_rounding is RoundingRule.HALF_UP_PAISA
    assert T.total_rounding is RoundingRule.HALF_UP_RUPEE


def test_every_component_has_terms_and_assumptions() -> None:
    for code in CALCULATED_CODES:
        terms = T.terms(code)
        assert terms.label
        assert terms.assumptions
        assert terms.source is None  # synthetic: nothing is sourced
        assert "no source (synthetic value)" in T.source_note(code)
    with pytest.raises(TariffError):
        T.terms(ComponentCode.OTHER)


def test_registry() -> None:
    assert get_tariff("SAMAY-DEMO-1") is T
    with pytest.raises(TariffError, match="unknown tariff"):
        get_tariff("UPPCL-HV2")
    with pytest.raises(TariffError):
        get_tariff(None)  # type: ignore[arg-type]


def _verified(**changes: Any) -> Tariff:
    source = SourceRef("Test order", "p. 1")
    components = tuple(dataclasses.replace(c, source=source) for c in T.components)
    fields: dict[str, Any] = {"status": DataStatus.VERIFIED, "components": components}
    fields.update(changes)
    return dataclasses.replace(T, **fields)


def test_verified_tariff_needs_every_source() -> None:
    tariff = _verified()
    assert not tariff.is_synthetic
    assert "Test order, p. 1" in tariff.source_note(ComponentCode.ENERGY_CHARGE)
    partly = (dataclasses.replace(tariff.components[0], source=None), *tariff.components[1:])
    with pytest.raises(TariffError, match="demand_charge"):
        dataclasses.replace(tariff, components=partly)


@pytest.mark.parametrize(
    "changes",
    [
        {"tariff_id": " "},
        {"status": "synthetic"},
        {"demand_rate": Rate.rupees_per("400", Unit.KVA)},  # wrong basis
        {"demand_rate": Rate.rupees_per("400", Unit.KVAH)},
        {"demand_rate": Rate.rupees_per("-1", Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD)},
        {"energy_rate": Rate.rupees_per("9", Unit.KWH)},
        {"energy_rate": "9"},
        {"demand_floor_percent": Decimal("75.125")},
        {"demand_floor_percent": Decimal(101)},
        {"duty_percent": Decimal(-1)},
        {"excess_demand_multiplier": Decimal("1.0001")},
        {"excess_demand_multiplier": Decimal(101)},
        {"tod_rates": T.tod_rates[:2]},
        {"tod_rates": (*T.tod_rates[:2], T.tod_rates[0])},
        {"tod_rates": list(T.tod_rates)},
        {"line_rounding": "HALF_UP"},
        {"components": T.components[:-1]},
        {"components": (*T.components, T.components[0])},
        {"components": ("x",)},
        {"assumptions": (("a", "b"),)},
    ],
)
def test_invalid_tariffs_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises((TariffError, TypeError, ValueError)):
        dataclasses.replace(T, **changes)


def test_part_validation() -> None:
    with pytest.raises(TariffError):
        SourceRef("", "p. 1")
    with pytest.raises(TariffError):
        Assumption("k", " ")
    with pytest.raises(TariffError):
        ComponentTerms(ComponentCode.OTHER, "x", ())
    with pytest.raises(TariffError):
        ComponentTerms(ComponentCode.ENERGY_CHARGE, "x", ["a"])  # type: ignore[arg-type]
    with pytest.raises(TariffError):
        ComponentTerms(ComponentCode.ENERGY_CHARGE, "x", (), source="p. 1")  # type: ignore[arg-type]
    with pytest.raises(TariffError):
        TodRate("peak", "18-22", Rate.rupees_per("1", Unit.KVAH))  # type: ignore[arg-type]
    with pytest.raises(TariffError):
        TodRate(TodZone.PEAK, "18-22", Rate.rupees_per("1", Unit.KWH))
    assert str(Assumption("k", "text")) == "[k] text"
    assert str(SourceRef("Order", "p. 2")) == "Order, p. 2"
