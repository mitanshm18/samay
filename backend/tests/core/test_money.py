"""Money, ExactAmount and Rate: worked examples with the arithmetic shown."""

from decimal import Decimal

import pytest

from samay.core import (
    ApparentEnergy,
    ApparentPower,
    Energy,
    ExactAmount,
    InvalidValueError,
    Money,
    PrecisionError,
    Rate,
    RoundingRule,
    Unit,
    UnitMismatchError,
)
from samay.core.money import MAX_ABS_PAISE

HALF_UP = RoundingRule.HALF_UP_PAISA


# ---- construction -----------------------------------------------------------


def test_from_paise_holds_int() -> None:
    assert Money.from_paise(73500).paise == 73500


@pytest.mark.parametrize(
    ("rupees", "paise"),
    [
        ("735", 73500),
        ("735.5", 73550),
        ("735.50", 73550),
        ("0.01", 1),
        ("-12.34", -1234),
        ("1e2", 10000),
        (" 7.35 ", 735),
        (Decimal("7.350000"), 735),  # trailing zeros are not extra precision
        (7, 700),
    ],
)
def test_from_rupees_exact(rupees: str | Decimal | int, paise: int) -> None:
    assert Money.from_rupees(rupees).paise == paise


def test_float_rupees_rejected() -> None:
    with pytest.raises(TypeError, match="float"):
        Money.from_rupees(7.35)  # type: ignore[arg-type]


def test_bool_rejected() -> None:
    with pytest.raises(TypeError):
        Money.from_rupees(True)


def test_other_types_rejected() -> None:
    with pytest.raises(TypeError, match="expected str, int or Decimal"):
        Money.from_rupees([1])  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["abc", "", "1,000"])
def test_unparseable_rejected(bad: str) -> None:
    with pytest.raises(InvalidValueError, match="not a number"):
        Money.from_rupees(bad)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-inf"])
def test_non_finite_rejected(bad: str) -> None:
    with pytest.raises(InvalidValueError, match="finite"):
        Money.from_rupees(bad)


def test_more_than_two_places_rejected_not_rounded() -> None:
    with pytest.raises(PrecisionError, match="round"):
        Money.from_rupees("7.355")


@pytest.mark.parametrize("bad", [7.0, Decimal(5), "5", True])
def test_constructor_needs_int_paise(bad: object) -> None:
    with pytest.raises(TypeError, match="int number of paise"):
        Money(bad)  # type: ignore[arg-type]


def test_range_limit() -> None:
    Money(MAX_ABS_PAISE - 1)
    with pytest.raises(InvalidValueError):
        Money(MAX_ABS_PAISE)
    with pytest.raises(InvalidValueError):
        Money.from_rupees("1e17")


# ---- arithmetic -------------------------------------------------------------


def test_add_sub_neg() -> None:
    a, b = Money(1050), Money(250)
    assert a + b == Money(1300)
    assert a - b == Money(800)
    assert -a == Money(-1050)
    assert b - a == Money(-800)


def test_sum_starts_from_zero() -> None:
    assert sum([Money(1), Money(2), Money(3)]) == Money(6)
    assert sum([], Money.zero()) == Money(0)


@pytest.mark.parametrize("other", [1, 1.0, Decimal(1), "1"])
def test_money_and_plain_numbers_do_not_mix(other: object) -> None:
    with pytest.raises(TypeError):
        Money(100) + other  # type: ignore[operator]
    with pytest.raises(TypeError):
        Money(100) - other  # type: ignore[operator]
    with pytest.raises(TypeError):
        other + Money(100)  # type: ignore[operator]


def test_money_times_money_rejected() -> None:
    with pytest.raises(TypeError):
        Money(100) * Money(2)  # type: ignore[operator]


def test_ordering_and_equality() -> None:
    assert Money(1) < Money(2) <= Money(2)
    assert Money(5) == Money(5)
    assert Money(5) != 5  # type: ignore[comparison-overlap]
    with pytest.raises(TypeError):
        _ = Money(1) < 2  # type: ignore[operator]
    assert len({Money(5), Money(5), Money(6)}) == 2


def test_to_rupees_is_exact() -> None:
    assert Money(73550).to_rupees() == Decimal("735.50")
    assert str(Money(-5).to_rupees()) == "-0.05"


# ---- percentages ------------------------------------------------------------


def test_apply_percent_exact() -> None:
    # ₹1,000.00 x 7.5% = 100000 x 0.075 = 7500 paise exactly.
    assert Money(100000).apply_percent("7.5", rule=HALF_UP) == Money(7500)


def test_apply_percent_needs_rounding() -> None:
    # ₹333.33 x 7.5% = 33333 x 0.075 = 2499.975 paise -> 2500 (half-up), 2499 (floor).
    assert Money(33333).apply_percent("7.5", rule=HALF_UP) == Money(2500)
    assert Money(33333).apply_percent("7.5", rule=RoundingRule.FLOOR_PAISA) == Money(2499)


def test_apply_percent_rule_is_required() -> None:
    with pytest.raises(TypeError):
        Money(100).apply_percent("5")  # type: ignore[call-arg]


def test_apply_percent_rejects_float_and_excess_precision() -> None:
    with pytest.raises(TypeError):
        Money(100).apply_percent(7.5, rule=HALF_UP)  # type: ignore[arg-type]
    with pytest.raises(PrecisionError):
        Money(100).apply_percent("7.1234567", rule=HALF_UP)
    with pytest.raises(InvalidValueError):
        Money(100).apply_percent("1e7", rule=HALF_UP)


# ---- allocation -------------------------------------------------------------


def test_allocate_equal_thirds() -> None:
    # 10000 / 3 = 3333 r 1 each; the one leftover paisa goes to the first part.
    assert Money(10000).allocate([1, 1, 1]) == (Money(3334), Money(3333), Money(3333))


def test_allocate_proportional() -> None:
    # 1000 paise by 1:2:7 -> 100, 200, 700 exactly.
    assert Money(1000).allocate([1, 2, 7]) == (Money(100), Money(200), Money(700))


def test_allocate_largest_remainder() -> None:
    # 100 paise by 1:1:1:3 (total 6): exact shares 16.67, 16.67, 16.67, 50.
    # Floors 16,16,16,50 = 98; the 2 leftover paise go to the first two (ties by position).
    assert Money(100).allocate([1, 1, 1, 3]) == (Money(17), Money(17), Money(16), Money(50))


def test_allocate_negative_and_zero_weight() -> None:
    assert Money(-10000).allocate([1, 1, 1]) == (Money(-3334), Money(-3333), Money(-3333))
    assert Money(101).allocate([0, 1, 1]) == (Money(0), Money(51), Money(50))


@pytest.mark.parametrize("weights", [[], [0, 0], [1, -1], [1.5], [True], "12"])
def test_allocate_rejects_bad_weights(weights: list[object]) -> None:
    with pytest.raises(InvalidValueError):
        Money(100).allocate(weights)  # type: ignore[arg-type]


# ---- display ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0.00"),
        (5, "₹0.05"),
        (-5, "-₹0.05"),
        (73500, "₹735.00"),
        (100000, "₹1,000.00"),
        (7350000, "₹73,500.00"),
        (12345678, "₹1,23,456.78"),
        (12345678901, "₹12,34,56,789.01"),
        (-10000000000, "-₹10,00,00,000.00"),
    ],
)
def test_indian_grouping(paise: int, text: str) -> None:
    assert Money(paise).format_inr() == text
    assert str(Money(paise)) == text


# ---- exact amounts and rates ------------------------------------------------


def test_rate_times_energy_worked_example() -> None:
    # ₹7.355/kWh = 735.5 paise/kWh.
    # 735.5 x 1,234.567 = 864,196.9 (x700) + 43,827.1285 (x35.5) = 908,024.0285 paise.
    # Half-up to the paisa: 908,024 paise = ₹9,080.24.
    rate = Rate.rupees_per("7.355", Unit.KWH)
    assert rate.paise_per_unit == Decimal("735.5")
    exact = rate * Energy("1234.567")
    assert exact.paise == Decimal("908024.0285")
    assert exact.round(HALF_UP) == Money(908024)
    assert exact.round(HALF_UP).format_inr() == "₹9,080.24"


def test_quantity_times_rate_also_works() -> None:
    assert Energy("2") * Rate.paise_per("100", Unit.KWH) == ExactAmount(Decimal(200))


def test_rate_unit_must_match() -> None:
    with pytest.raises(UnitMismatchError, match="per kWh"):
        Rate.rupees_per("7", Unit.KWH) * ApparentEnergy("10")
    with pytest.raises(UnitMismatchError):
        Rate.rupees_per("450", Unit.KVA) * ApparentEnergy("10")
    assert Rate.rupees_per("450", Unit.KVA) * ApparentPower("10") == ExactAmount(Decimal(450000))


def test_rate_times_non_quantity_rejected() -> None:
    with pytest.raises(TypeError):
        Rate.paise_per(1, Unit.KWH) * 5  # type: ignore[operator]


def test_rate_validation() -> None:
    with pytest.raises(TypeError):
        Rate(7.0, Unit.KWH)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Rate(Decimal(1), "kWh")  # type: ignore[arg-type]
    with pytest.raises(PrecisionError):
        Rate.paise_per("0.0000001", Unit.KWH)
    with pytest.raises(InvalidValueError):
        Rate.rupees_per("1e8", Unit.KWH)
    with pytest.raises(TypeError):
        Rate.rupees_per(7.35, Unit.KWH)  # type: ignore[arg-type]
    assert str(Rate.rupees_per("-0.5", Unit.KWH)) == "-50.0 paise/kWh"  # rebates allowed


def test_exact_amount_needs_explicit_rule() -> None:
    exact = ExactAmount(Decimal("10.5"))
    with pytest.raises(TypeError):
        exact.round()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        exact.round("HALF_UP")  # type: ignore[arg-type]
    assert exact.round(HALF_UP) == Money(11)
    assert exact.round(RoundingRule.HALF_EVEN_PAISA) == Money(10)


def test_exact_amount_arithmetic_stays_exact() -> None:
    a = ExactAmount(Decimal("0.4"))
    total = a + a + a  # 1.2 paise; rounding each first would give 0 + 0 + 0
    assert total == ExactAmount(Decimal("1.2"))
    assert total.round(HALF_UP) == Money(1)
    assert (a - total) == ExactAmount(Decimal("-0.8"))
    assert -a == ExactAmount(Decimal("-0.4"))
    assert Money(150).to_exact() + ExactAmount(Decimal("0.5")) == ExactAmount(Decimal("150.5"))


def test_exact_amount_validation() -> None:
    with pytest.raises(TypeError):
        ExactAmount(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ExactAmount(Decimal("NaN"))
    with pytest.raises(InvalidValueError):
        ExactAmount(Decimal("1e18"))
    with pytest.raises(TypeError):
        ExactAmount(Decimal(1)) + Money(1)  # type: ignore[operator]
    with pytest.raises(TypeError):
        ExactAmount(Decimal(1)) - Money(1)  # type: ignore[operator]
    with pytest.raises(TypeError):
        ExactAmount.from_rupees(1.5)  # type: ignore[arg-type]
    with pytest.raises(InvalidValueError):
        ExactAmount.from_rupees("1e17")


def test_exact_amount_from_rupees_allows_extra_precision() -> None:
    # ₹7.355 = 735.5 paise; becomes Money only with a rule.
    assert ExactAmount.from_rupees("7.355").round(HALF_UP) == Money(736)
