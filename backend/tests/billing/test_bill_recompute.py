"""Bill recalculation with SAMAY-DEMO-1: worked examples with the arithmetic shown.

Rates in paise: demand 40000/kVA, excess 40000 x 1.5 = 60000/kVA, energy 900/kVAh,
ToD peak +150, off-peak -100, normal 0 per kVAh. Duty 5%.
"""

import dataclasses
from decimal import Decimal

import pytest
from bills import SYN, VER, bill, entered, other, zones

from samay.billing import (
    BillBreakdown,
    BillValidationError,
    LineBasis,
    MoneyLine,
    PrintedLine,
    ZoneConsumption,
    recompute_bill,
)
from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    ExactAmount,
    ExactApparentPower,
    MissingValueError,
    Money,
    Provenance,
    RoundingRule,
    Traced,
)
from samay.tariffs import SAMAY_DEMO_1, ComponentCode, SourceRef, Tariff

C = ComponentCode


def paise(line: MoneyLine) -> int:
    return line.amount.value.paise


def amounts(result: BillBreakdown) -> list[int]:
    return [paise(line) for line in result.lines]


def verified_tariff() -> Tariff:
    source = SourceRef("Test order (fictional)", "p. 1")
    components = tuple(dataclasses.replace(c, source=source) for c in SAMAY_DEMO_1.components)
    return dataclasses.replace(
        SAMAY_DEMO_1, status=DataStatus.VERIFIED, components=components, assumptions=()
    )


# ---- worked example A: demand above the floor, no excess ------------------------


def test_worked_example_a() -> None:
    result = recompute_bill(bill(), SAMAY_DEMO_1)
    # C1 billing demand = max(412.345, 75% x 500 = 375) = 412.345 kVA
    assert result.quantity("billing_demand").value.value == ExactApparentPower(Decimal("412.345"))
    # C2 = 40000 x 412.345 = 16,493,800 paise
    assert paise(result.line(C.DEMAND_CHARGE)) == 16_493_800
    # C3 = 0 (MD below CD)
    assert paise(result.line(C.EXCESS_DEMAND_CHARGE)) == 0
    # C4 = 900 x 100,000 = 90,000,000
    assert paise(result.line(C.ENERGY_CHARGE)) == 90_000_000
    # C5 = 150 x 25,000 - 100 x 30,000 + 0 x 45,000 = 3,750,000 - 3,000,000 = 750,000
    assert paise(result.line(C.TOD_ADJUSTMENT)) == 750_000
    # C6 = 5% x (16,493,800 + 0 + 90,000,000 + 750,000) = 5% x 107,243,800 = 5,362,190
    assert paise(result.line(C.ELECTRICITY_DUTY)) == 5_362_190
    # C8 = 107,243,800 + 5,362,190 = 112,605,990 (₹11,26,059.90)
    assert result.subtotal.value == Money(112_605_990)
    # C9 = 112,606,000 - 112,605,990 = +10 paise; total ₹11,26,060.00
    assert paise(result.rounding_off) == 10
    assert result.total.value == Money(112_606_000)
    assert result.total.value.format_inr() == "₹11,26,060.00"
    assert sum(amounts(result)) == 112_606_000


# ---- worked example B: the 75% floor applies, kept exact -----------------------------


def test_worked_example_b_exact_floor() -> None:
    result = recompute_bill(
        bill(cd="100.123", md="60.5", kwh="9000", kvah="10000", tod=zones("0", "0", "10000")),
        SAMAY_DEMO_1,
    )
    # Floor = 75% x 100.123 = 75.09225 kVA (5 places, not rounded); MD 60.5 is lower.
    assert result.quantity("demand_floor").value.value == ExactApparentPower(Decimal("75.09225"))
    # C2 = 40000 x 75.09225 = 3,003,690 paise exactly (no rounding needed).
    demand = result.line(C.DEMAND_CHARGE)
    assert demand.exact is not None
    assert demand.exact.value == ExactAmount(Decimal(3_003_690))
    assert paise(demand) == 3_003_690
    # C4 = 900 x 10,000 = 9,000,000; C5 = 0.
    # C6 = 5% x 12,003,690 = 600,184.5 -> half-up 600,185.
    duty = result.line(C.ELECTRICITY_DUTY)
    assert duty.exact is not None
    assert duty.exact.value == ExactAmount(Decimal("600184.5"))
    assert paise(duty) == 600_185
    # C8 = 12,003,690 + 600,185 = 12,603,875 -> rupee half-up 12,603,900; C9 = +25.
    assert paise(result.rounding_off) == 25
    assert result.total.value == Money(12_603_900)


def test_floor_of_odd_contract_demand_rounds_only_the_money() -> None:
    # 75% x 0.001 kVA = 0.00075 kVA; C2 = 40000 x 0.00075 = 30 paise exactly.
    result = recompute_bill(
        bill(cd="0.001", md="0", kwh="0", kvah="0", tod=zones("0", "0", "0")), SAMAY_DEMO_1
    )
    assert paise(result.line(C.DEMAND_CHARGE)) == 30


# ---- worked example C: excess demand, a pass-through line, ties -----------------


def test_worked_example_c() -> None:
    result = recompute_bill(
        bill(
            md="512.345",
            kwh="90000.5",
            kvah="100000.123",
            tod=zones("20000.041", "30000.07", "50000.012"),
            printed=(other("Meter rent", "250"),),
        ),
        SAMAY_DEMO_1,
    )
    # C1 = max(512.345, 375) = 512.345; C2 = 40000 x 512.345 = 20,493,800
    # C3 = (512.345 - 500) x 60000 = 12.345 x 60000 = 740,700
    # C4 = 900 x 100,000.123 = 90,000,110.7 -> 90,000,111
    # C5 = 150 x 20,000.041 - 100 x 30,000.07 + 0 = 3,000,006.15 - 3,000,007 = -0.85 -> -1
    # C6 = 5% x (20,493,800 + 740,700 + 90,000,111 - 1) = 5% x 111,234,610
    #    = 5,561,730.5, a tie -> half-up 5,561,731
    # C7 = meter rent 25,000 as printed
    # C8 = 111,234,610 + 5,561,731 + 25,000 = 116,821,341; C9 = 116,821,300 - C8 = -41
    assert amounts(result) == [
        20_493_800,
        740_700,
        90_000_111,
        -1,
        5_561_731,
        25_000,
        -41,
    ]
    assert result.total.value == Money(116_821_300)
    tod = result.line(C.TOD_ADJUSTMENT)
    assert tod.exact is not None
    assert tod.exact.value == ExactAmount(Decimal("-0.85"))
    assert result.quantity("excess_demand").value.value == ApparentPower("12.345")


def test_each_line_rounded_once_with_the_tariff_rule() -> None:
    result = recompute_bill(
        bill(kvah="100000.123", kwh="1", tod=zones("25000.123", "30000", "45000")), SAMAY_DEMO_1
    )
    for line in result.charges:
        assert line.rounding is RoundingRule.HALF_UP_PAISA
        assert line.exact is not None
        assert line.amount.value == line.exact.value.round(RoundingRule.HALF_UP_PAISA)
    assert result.rounding_off.rounding is RoundingRule.HALF_UP_RUPEE


def test_negative_subtotal_rounds_half_up_away_from_zero() -> None:
    # All energy off-peak with a large rebate printed line: subtotal goes negative.
    # 0 kVA demand floor: CD 0.001, MD 0. kVAh 0. Rebate printed as -₹10.50.
    result = recompute_bill(
        bill(
            cd="0.001",
            md="0",
            kwh="0",
            kvah="0",
            tod=zones("0", "0", "0"),
            printed=(other("Rebate", "-10.80"),),
        ),
        SAMAY_DEMO_1,
    )
    # C2 = 30 paise; duty = 5% x 30 = 1.5 -> 2; C7 = -1080. C8 = 30 + 2 - 1080 = -1048.
    # Rupee half-up of -1048 = -1000 (-10.48 rupees -> -10); C9 = +48.
    assert result.subtotal.value == Money(-1048)
    assert paise(result.rounding_off) == 48
    assert result.total.value == Money(-1000)


# ---- pass-through lines (C7) --------------------------------------------------------


def test_pass_through_lines_are_kept_as_printed() -> None:
    rent = other("Meter rent", "250")
    extracted = PrintedLine(
        C.OTHER, "Late fee", Traced.extracted(Money(1234), source="bill p.1", status=VER)
    )
    printed_energy = PrintedLine(C.ENERGY_CHARGE, "Energy", entered(Money(1)))
    result = recompute_bill(bill(printed=(rent, extracted, printed_energy)), SAMAY_DEMO_1)
    passed = [line for line in result.charges if line.basis is LineBasis.NOT_RECALCULATED]
    assert [line.label for line in passed] == ["Meter rent", "Late fee"]
    assert passed[1].amount.provenance is Provenance.EXTRACTED
    assert passed[1].exact is None
    assert passed[1].rounding is None
    assert passed[1].formula == "taken as printed, not recalculated"
    # A printed energy line is not a pass-through: SAMAY recalculates energy itself.
    assert paise(result.line(C.ENERGY_CHARGE)) == 90_000_000
    assert result.not_recalculated_total.value == Money(25_000 + 1234)
    # Duty is on C2..C5 only, so it does not change with pass-through lines.
    plain = recompute_bill(bill(), SAMAY_DEMO_1)
    assert paise(result.line(C.ELECTRICITY_DUTY)) == paise(plain.line(C.ELECTRICITY_DUTY))
    assert plain.not_recalculated_total.value == Money.zero()


def test_line_lookup() -> None:
    result = recompute_bill(bill(printed=(other("a", "1"), other("b", "2"))), SAMAY_DEMO_1)
    with pytest.raises(KeyError):
        result.line(C.OTHER)
    with pytest.raises(KeyError):
        result.quantity("nope")


# ---- missing data is never zero ---------------------------------------------------------


def assert_total_missing(result: BillBreakdown) -> None:
    assert result.subtotal.is_missing
    assert result.rounding_off.is_missing
    assert result.total.is_missing
    assert not result.is_complete
    with pytest.raises(MissingValueError):
        _ = result.total.value


def test_no_zone_data_makes_tod_and_total_missing() -> None:
    result = recompute_bill(bill(zones=None), SAMAY_DEMO_1)
    tod = result.line(C.TOD_ADJUSTMENT)
    assert tod.is_missing
    assert "ToD zone readings not provided" in tod.amount.note
    assert result.line(C.ELECTRICITY_DUTY).is_missing
    assert_total_missing(result)
    assert "ToD zone readings not provided" in result.total.note
    # Lines that do not need zones are still calculated.
    assert paise(result.line(C.ENERGY_CHARGE)) == 90_000_000
    assert any(i.code == "tod-zones-missing" for i in result.issues)


def test_partial_zone_data_makes_total_missing() -> None:
    partial = ZoneConsumption(
        entered(ApparentEnergy("25000")),
        Traced.missing(reason="off-peak not printed", status=VER, kind=ApparentEnergy),
        entered(ApparentEnergy("45000")),
    )
    result = recompute_bill(bill(tod=partial), SAMAY_DEMO_1)
    assert result.line(C.TOD_ADJUSTMENT).is_missing
    assert_total_missing(result)
    assert "off-peak not printed" in result.total.note
    assert any(i.code == "tod-zones-partial" for i in result.issues)


def test_missing_md_makes_demand_lines_missing() -> None:
    result = recompute_bill(
        bill(md=Traced.missing(reason="MD not printed", status=VER, kind=ApparentPower)),
        SAMAY_DEMO_1,
    )
    assert result.quantity("billing_demand").value.is_missing
    assert result.line(C.DEMAND_CHARGE).is_missing
    assert result.line(C.EXCESS_DEMAND_CHARGE).is_missing
    assert "MISSING" in result.line(C.DEMAND_CHARGE).formula
    assert_total_missing(result)


def test_missing_kvah_with_zones() -> None:
    result = recompute_bill(
        bill(kvah=Traced.missing(reason="kVAh unreadable", status=VER, kind=ApparentEnergy)),
        SAMAY_DEMO_1,
    )
    assert result.line(C.ENERGY_CHARGE).is_missing
    assert not result.line(C.TOD_ADJUSTMENT).is_missing  # zones are still known
    assert result.quantity("power_factor").value.is_missing
    assert {i.code for i in result.issues} >= {"tod-zones-unchecked", "input-missing"}
    assert_total_missing(result)


def test_missing_printed_other_line_makes_total_missing() -> None:
    unknown = PrintedLine(
        C.OTHER, "Arrears", Traced.missing(reason="illegible", status=VER, kind=Money)
    )
    result = recompute_bill(bill(printed=(unknown,)), SAMAY_DEMO_1)
    assert not result.line(C.ELECTRICITY_DUTY).is_missing
    assert_total_missing(result)
    assert result.not_recalculated_total.is_missing


# ---- status, assumptions and display -----------------------------------------------


def test_synthetic_tariff_makes_every_calculated_line_synthetic() -> None:
    result = recompute_bill(bill(printed=(other("Meter rent", "250"),)), SAMAY_DEMO_1)
    assert result.banner is not None
    assert "SYNTHETIC" in result.banner
    assert "not a real bill" in result.banner
    for line in result.lines:
        if line.basis is LineBasis.RECALCULATED:
            assert line.amount.is_synthetic
    # The pass-through line keeps its own (verified) status, but the total is synthetic.
    assert not result.charges[-1].amount.is_synthetic
    assert result.total.is_synthetic
    assert result.tariff_status is DataStatus.SYNTHETIC
    assert any(i.code == "synthetic-tariff" for i in result.issues)


def test_verified_tariff_and_inputs_give_a_verified_total() -> None:
    tariff = verified_tariff()
    result = recompute_bill(bill(), tariff)
    assert result.banner is None
    assert not result.total.is_synthetic
    assert result.total.value == Money(112_606_000)  # same numbers as example A
    assert "Test order (fictional), p. 1" in result.line(C.ENERGY_CHARGE).exact.inputs[0].note  # type: ignore[union-attr]
    synthetic_input = recompute_bill(bill(status=SYN), tariff)
    assert synthetic_input.total.is_synthetic


def test_assumptions_are_listed_once() -> None:
    result = recompute_bill(bill(), SAMAY_DEMO_1)
    keys = [a.key for a in result.assumptions]
    assert len(keys) == len(set(keys))
    assert {"synthetic", "demand-floor", "tod-zones", "total-rounding", "power-factor"} <= set(keys)
    assert result.line(C.DEMAND_CHARGE).assumptions


def test_formulas_show_the_working() -> None:
    result = recompute_bill(bill(), SAMAY_DEMO_1)
    assert result.line(C.DEMAND_CHARGE).formula == (
        "₹400.00/kVA per billing period x billing demand 412.345 kVA = ₹1,64,938.00"
    )
    assert result.line(C.ENERGY_CHARGE).formula == "₹9.00/kVAh x 100000 kVAh = ₹9,00,000.00"
    assert result.rounding_off.formula.endswith("= ₹0.10")
    assert result.quantity("power_factor").formula == (
        "kWh 90000 kWh / kVAh 100000 kVAh = 0.900 (shown to 3 places, half-up)"
    )


def test_power_factor_is_information_only() -> None:
    low = recompute_bill(bill(kwh="50000"), SAMAY_DEMO_1)
    high = recompute_bill(bill(kwh="100000"), SAMAY_DEMO_1)
    assert low.total.value == high.total.value
    assert low.quantity("power_factor").value.value.ratio == Decimal("0.5")
    zero = recompute_bill(bill(kwh="0", kvah="0", tod=zones("0", "0", "0")), SAMAY_DEMO_1)
    assert "kVAh is 0" in zero.quantity("power_factor").value.note


def test_errors_stop_the_calculation() -> None:
    with pytest.raises(BillValidationError) as caught:
        recompute_bill(bill(kwh="100001"), SAMAY_DEMO_1)
    assert [i.code for i in caught.value.issues] == ["kwh-above-kvah"]
    assert "kwh-above-kvah" in str(caught.value)
