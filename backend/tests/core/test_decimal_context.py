"""Regression tests: Python's shared decimal context cannot change SAMAY's results.

Python's decimal operators use the thread's current context, which any code
can change (decimal.getcontext().prec = 4). Before the fix, the worked bill
example below gave 908,343 paise instead of 908,024 under precision 4, with no
error. Every test here changes the shared context on purpose, runs the core,
and requires exactly the results computed under Python's defaults.

Each change is undone in a finally block, and conftest.py fails any test that
leaks a modified context.
"""

from __future__ import annotations

import decimal
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_UP, Decimal
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    Duration,
    Energy,
    ExactAmount,
    IntervalReading,
    MeterInterval,
    Money,
    Power,
    PowerFactor,
    PrecisionError,
    QuantityRounding,
    Rate,
    RoundingRule,
    Traced,
    Unit,
    average_power_factor,
    round_paise,
)

HALF_UP = RoundingRule.HALF_UP_PAISA


@contextmanager
def shared_context(**settings: object) -> Iterator[decimal.Context]:
    """Change the thread's shared decimal context in place, then restore it exactly."""
    ctx = decimal.getcontext()
    saved = ctx.copy()
    try:
        for name, value in settings.items():
            setattr(ctx, name, value)
        yield ctx
    finally:
        decimal.setcontext(saved)


# Hostile settings that each broke at least one operation before the fix.
HOSTILE = [
    pytest.param({"prec": 4}, id="prec4"),
    pytest.param({"prec": 4, "rounding": ROUND_DOWN}, id="prec4-down"),
    pytest.param({"prec": 1, "rounding": ROUND_FLOOR}, id="prec1-floor"),
    pytest.param({"prec": 2, "rounding": ROUND_CEILING}, id="prec2-ceiling"),
    pytest.param(
        {"prec": 3, "rounding": ROUND_UP, "Emax": 10, "Emin": -10}, id="prec3-tiny-exponent"
    ),
]


def test_the_original_failure_is_fixed() -> None:
    # Exact reproduction of the review finding: global precision 4.
    with shared_context(prec=4):
        amount = (Rate.rupees_per("7.355", Unit.KWH) * Energy("1234.567")).round(HALF_UP)
    assert amount == Money(908024)  # was Money(908343) before the fix


@pytest.mark.parametrize("settings", HOSTILE)
def test_worked_bill_example(settings: dict[str, object]) -> None:
    with shared_context(**settings):
        energy = Energy("1234.567")
        exact = Rate.rupees_per("7.355", Unit.KWH) * energy
        amount = exact.round(HALF_UP)
    assert energy.value == Decimal("1234.567")
    assert exact.paise == Decimal("908024.0285")
    assert amount == Money(908024)
    assert amount.format_inr() == "₹9,080.24"


@pytest.mark.parametrize("settings", HOSTILE)
def test_each_previously_affected_operation(settings: dict[str, object]) -> None:
    with shared_context(**settings):
        quantity = Energy("12345.678")  # was number + 0
        rupees = Money(12345678).to_rupees()  # was scaleb
        negated = -ExactAmount(Decimal("123456.5"))  # was unary minus
        pf = PowerFactor(Fraction(2, 3)).rounded(6, rounding=QuantityRounding.HALF_UP)  # scaleb
        largest = Energy("999999999999999.999")  # abs() in the range check
    assert quantity.value == Decimal("12345.678")
    assert str(quantity) == "12345.678 kWh"
    assert rupees == Decimal("123456.78")
    assert str(rupees) == "123456.78"
    assert negated == ExactAmount(Decimal("-123456.5"))
    assert str(pf) == "0.666667"
    assert largest.value == Decimal("999999999999999.999")


@pytest.mark.parametrize("settings", HOSTILE)
def test_rounding_table_unchanged(settings: dict[str, object]) -> None:
    cases = [
        ("12.5", RoundingRule.HALF_UP_PAISA, 13),
        ("-12.5", RoundingRule.HALF_UP_PAISA, -13),
        ("12.5", RoundingRule.HALF_EVEN_PAISA, 12),
        ("13.5", RoundingRule.HALF_EVEN_PAISA, 14),
        ("12.0001", RoundingRule.CEIL_PAISA, 13),
        ("-12.0001", RoundingRule.FLOOR_PAISA, -13),
        ("12350", RoundingRule.HALF_UP_RUPEE, 12400),
        ("123456789012.5", RoundingRule.HALF_UP_PAISA, 123456789013),
    ]
    with shared_context(**settings):
        results = [round_paise(Decimal(a), rule) for a, rule, _ in cases]
    assert results == [expected for _, _, expected in cases]


@pytest.mark.parametrize("settings", HOSTILE)
def test_every_core_operation_matches_defaults(settings: dict[str, object]) -> None:
    def run() -> list[object]:
        interval = MeterInterval(
            "HT-001", datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
        )
        bill = Traced.extracted(
            Energy("123456.789"), source="test bill", status=DataStatus.VERIFIED
        )
        rate = Traced.extracted(
            Rate.rupees_per("8.125", Unit.KWH), source="SAMAY-DEMO-1", status=DataStatus.SYNTHETIC
        )
        charge = Traced.derive(lambda r, q: (r * q).round(HALF_UP), rate, bill, description="x")
        return [
            Money.from_rupees("98765432.10"),
            Money(98765432101).apply_percent("7.5", rule=HALF_UP),
            Money(98765432101).allocate([3, 7, 11]),
            Money(98765432101).format_inr(),
            ExactAmount.from_rupees("1234567.891") + ExactAmount(Decimal("0.0005")),
            Energy.from_mwh("12345.678"),
            Energy("99999.999") - Energy("0.001"),
            Duration.from_minutes(45),
            Power("12345.678") * Duration("0.5"),
            ApparentPower("2345.6").energy_over(
                Duration("0.333"), rounding=QuantityRounding.HALF_UP
            ),
            average_power_factor(
                IntervalReading(Energy("98765.432"), interval),
                IntervalReading(ApparentEnergy("123456.789"), interval),
            ).rounded(4, rounding=QuantityRounding.HALF_EVEN),
            charge.value,
            charge.status,
        ]

    expected = run()  # Python's defaults
    with shared_context(**settings):
        actual = run()
    assert actual == expected


money_paise = st.integers(min_value=-(10**15), max_value=10**15)
rupee_rate = st.decimals(
    min_value=-1000, max_value=10**5, places=4, allow_nan=False, allow_infinity=False
)
kwh = st.decimals(min_value=0, max_value=10**9, places=3, allow_nan=False, allow_infinity=False)
rules = st.sampled_from(list(RoundingRule))
precisions = st.integers(min_value=1, max_value=27)
modes = st.sampled_from([ROUND_DOWN, ROUND_UP, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN])


@given(money_paise, rupee_rate, kwh, rules, precisions, modes)
def test_results_independent_of_shared_context(
    paise: int, rate: Decimal, energy: Decimal, rule: RoundingRule, prec: int, mode: str
) -> None:
    def run() -> tuple[object, ...]:
        exact = Rate.rupees_per(rate, Unit.KWH) * Energy(energy)
        money = Money(paise)
        return (
            exact.paise,
            exact.round(rule),
            (-exact).round(rule),
            money.to_rupees(),
            money.apply_percent("18", rule=rule),
            Energy(energy).value,
        )

    expected = run()
    with shared_context(prec=prec, rounding=mode):
        actual = run()
    assert actual == expected


def test_context_is_restored_after_failure() -> None:
    before = decimal.getcontext().prec
    with pytest.raises(RuntimeError), shared_context(prec=2):
        raise RuntimeError("boom")
    assert decimal.getcontext().prec == before


def test_localcontext_also_cannot_change_results() -> None:
    with decimal.localcontext(prec=3, rounding=ROUND_HALF_EVEN):
        amount = (Rate.rupees_per("7.355", Unit.KWH) * Energy("1234.567")).round(HALF_UP)
    assert amount == Money(908024)


# ---- the second silent-rounding path found during the fix ---------------------


def test_no_double_rounding_just_below_a_tie() -> None:
    # 12.4999...9 (120 nines) is below 12.5, so HALF_UP must give 12, never 13.
    # Before the fix, a context that rounded silently turned it into 12.5 first.
    just_below = Decimal("12.4" + "9" * 120)
    with pytest.raises(PrecisionError, match="too many digits"):
        round_paise(just_below, HALF_UP)
    near = Decimal("12.4" + "9" * 90)  # still exact within the core's precision
    assert round_paise(near, HALF_UP) == 12


def test_exact_amount_precision_is_bounded() -> None:
    ExactAmount(Decimal("1.000000000001"))  # 12 places: allowed
    with pytest.raises(PrecisionError):
        ExactAmount(Decimal("1.0000000000001"))  # 13 places: refused, not rounded
