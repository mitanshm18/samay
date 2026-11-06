"""Electricity quantities: units never mix, precision is never lost."""

from decimal import Decimal
from fractions import Fraction

import pytest

from samay.core import (
    ApparentEnergy,
    ApparentPower,
    Duration,
    Energy,
    InvalidValueError,
    Power,
    PowerFactor,
    PrecisionError,
    QuantityRounding,
    ReactiveEnergy,
    UnitMismatchError,
)
from samay.core.units import Quantity

ALL = [Energy, ApparentEnergy, ReactiveEnergy, Power, ApparentPower, Duration]


@pytest.mark.parametrize("cls", ALL)
def test_construct_from_str_int_decimal(cls: type[Quantity]) -> None:
    assert cls("1.5").value == Decimal("1.5")
    assert cls(2).value == Decimal(2)
    assert cls(Decimal("0.125")).value == Decimal("0.125")
    assert cls.zero().value == 0


@pytest.mark.parametrize("cls", ALL)
def test_float_rejected(cls: type[Quantity]) -> None:
    with pytest.raises(TypeError, match="float"):
        cls(1.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("cls", ALL)
def test_negative_rejected(cls: type[Quantity]) -> None:
    with pytest.raises(InvalidValueError, match="negative"):
        cls("-0.001")


def test_negative_zero_normalised() -> None:
    assert str(Energy("-0")) == "0 kWh"


@pytest.mark.parametrize("bad", ["0.0001", "1.2345", Decimal("0.0005")])
def test_excess_precision_rejected_not_rounded(bad: str | Decimal) -> None:
    with pytest.raises(PrecisionError, match="3 decimal places"):
        Energy(bad)


def test_trailing_zeros_are_not_precision() -> None:
    assert Energy("1.2300000").value == Decimal("1.23")


@pytest.mark.parametrize("bad", ["NaN", "inf", "x"])
def test_non_numbers_rejected(bad: str) -> None:
    with pytest.raises(InvalidValueError):
        Energy(bad)


def test_magnitude_limit() -> None:
    with pytest.raises(InvalidValueError, match="range"):
        Energy("1e15")


def test_same_unit_arithmetic() -> None:
    assert Energy("1.5") + Energy("2.25") == Energy("3.75")
    assert Energy("5") - Energy("1.5") == Energy("3.5")
    assert Power("10") > Power("9.999")
    assert Power("10") >= Power("10")
    assert Power("1") < Power("2")
    assert Power("2") <= Power("2")


def test_subtraction_never_goes_negative() -> None:
    with pytest.raises(InvalidValueError, match="negative"):
        Energy("1") - Energy("2")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (Energy("1"), ApparentEnergy("1")),
        (Power("1"), ApparentPower("1")),
        (Energy("1"), Power("1")),
        (ReactiveEnergy("1"), Energy("1")),
        (Duration("1"), Energy("1")),
    ],
)
def test_units_never_mix(a: Quantity, b: Quantity) -> None:
    with pytest.raises(UnitMismatchError):
        a + b
    with pytest.raises(UnitMismatchError):
        a - b
    with pytest.raises(UnitMismatchError):
        _ = a < b
    with pytest.raises(UnitMismatchError):
        _ = a <= b
    with pytest.raises(UnitMismatchError):
        _ = a > b
    with pytest.raises(UnitMismatchError):
        _ = a >= b
    assert a != b


def test_quantity_and_plain_number_do_not_mix() -> None:
    with pytest.raises(TypeError):
        Energy("1") + 1  # type: ignore[operator]
    with pytest.raises(TypeError):
        Energy("1") - Decimal(1)  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = Energy("1") < 2  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = Energy("1") <= 2  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = Energy("1") > 2  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = Energy("1") >= 2  # type: ignore[operator]
    assert Energy("1") != 1


def test_energy_divided_by_apparent_energy_is_refused() -> None:
    with pytest.raises(UnitMismatchError, match="average_power_factor"):
        Energy("900") / ApparentEnergy("1000")


def test_equality_and_hash() -> None:
    assert Energy("1.0") == Energy("1")
    assert hash(Energy("1.0")) == hash(Energy("1"))
    assert Energy("1") != ApparentEnergy("1")
    assert len({Energy("1"), Energy("1.000"), ApparentEnergy("1")}) == 2


def test_repr_and_str() -> None:
    assert repr(Energy("1.5")) == "Energy('1.5')"
    assert str(ApparentPower("250")) == "250 kVA"
    assert str(Duration("0.25")) == "0.25 h"
    assert str(ReactiveEnergy("3")) == "3 kVArh"


# ---- conversions ------------------------------------------------------------


def test_mega_units() -> None:
    assert Energy.from_mwh("1.2345") == Energy("1234.5")
    assert ApparentEnergy.from_mvah("0.001") == ApparentEnergy("1")
    assert Power.from_mw("2.5") == Power("2500")
    with pytest.raises(PrecisionError):
        Energy.from_mwh("0.0000001")


@pytest.mark.parametrize(("minutes", "hours"), [(15, "0.25"), (30, "0.5"), (6, "0.1"), (90, "1.5")])
def test_duration_from_minutes(minutes: int, hours: str) -> None:
    assert Duration.from_minutes(minutes) == Duration(hours)


@pytest.mark.parametrize("minutes", [20, 7, "0.0000001"])
def test_duration_from_minutes_refuses_inexact(minutes: int | str) -> None:
    # 20 minutes = 0.3333... h, which cannot be held exactly at 3 decimal places.
    with pytest.raises(PrecisionError):
        Duration.from_minutes(minutes)


# ---- power x time -----------------------------------------------------------


def test_power_times_duration() -> None:
    assert Power("100") * Duration("1.5") == Energy("150")
    assert Duration("1.5") * Power("100") == Energy("150")
    assert ApparentPower("200") * Duration("0.25") == ApparentEnergy("50")
    assert Duration("0.25") * ApparentPower("200") == ApparentEnergy("50")


def test_power_times_duration_refuses_inexact_result() -> None:
    # 1.001 kW x 0.333 h = 0.333333 kWh: more than 3 places, so it is refused.
    with pytest.raises(PrecisionError, match="energy_over"):
        Power("1.001") * Duration("0.333")
    with pytest.raises(PrecisionError):
        ApparentPower("1.001") * Duration("0.333")


def test_energy_over_rounds_explicitly() -> None:
    # 1.001 x 0.333 = 0.333333 -> 0.333 (both rules).
    assert Power("1.001").energy_over(
        Duration("0.333"), rounding=QuantityRounding.HALF_UP
    ) == Energy("0.333")
    # 0.5 x 0.001 = 0.0005: a tie at the 4th place -> 0.001 (half-up), 0.000 (half-even).
    assert Power("0.5").energy_over(Duration("0.001"), rounding=QuantityRounding.HALF_UP) == Energy(
        "0.001"
    )
    assert Power("0.5").energy_over(
        Duration("0.001"), rounding=QuantityRounding.HALF_EVEN
    ) == Energy("0")
    assert ApparentPower("0.5").energy_over(
        Duration("0.001"), rounding=QuantityRounding.HALF_UP
    ) == ApparentEnergy("0.001")


def test_energy_over_needs_duration() -> None:
    with pytest.raises(UnitMismatchError):
        Power("1").energy_over(Energy("1"), rounding=QuantityRounding.HALF_UP)  # type: ignore[arg-type]
    with pytest.raises(UnitMismatchError):
        ApparentPower("1").energy_over(Power("1"), rounding=QuantityRounding.HALF_UP)  # type: ignore[arg-type]


def test_power_times_wrong_type() -> None:
    with pytest.raises(TypeError):
        Power("1") * Power("1")  # type: ignore[operator]
    with pytest.raises(TypeError):
        ApparentPower("1") * 2  # type: ignore[operator]


# ---- power factor -----------------------------------------------------------


def test_power_factor_range() -> None:
    assert PowerFactor("0.95").ratio == Fraction(19, 20)
    assert PowerFactor(1).ratio == 1
    assert PowerFactor(0).ratio == 0
    assert PowerFactor(Fraction(2, 3)).ratio == Fraction(2, 3)
    bad_values: list[str | Fraction] = ["95", "-0.1", "1.0001", Fraction(4, 3)]
    for bad in bad_values:
        with pytest.raises(InvalidValueError, match="0 to 1"):
            PowerFactor(bad)
    with pytest.raises(TypeError):
        PowerFactor(0.95)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("ratio", "places", "half_up", "half_even"),
    [
        (Fraction(9, 10), 2, "0.90", "0.90"),
        (Fraction(2, 3), 3, "0.667", "0.667"),
        (Fraction(1, 8), 2, "0.13", "0.12"),  # 0.125: a tie
        (Fraction(3, 8), 2, "0.38", "0.38"),  # 0.375: tie, 0.38 is even
        (Fraction(1, 3), 0, "0", "0"),
        (Fraction(1, 1), 3, "1.000", "1.000"),
    ],
)
def test_power_factor_rounded(ratio: Fraction, places: int, half_up: str, half_even: str) -> None:
    pf = PowerFactor(ratio)
    assert str(pf.rounded(places, rounding=QuantityRounding.HALF_UP)) == half_up
    assert str(pf.rounded(places, rounding=QuantityRounding.HALF_EVEN)) == half_even


@pytest.mark.parametrize("places", [-1, 7, True])
def test_power_factor_rounded_places(places: int) -> None:
    with pytest.raises(InvalidValueError):
        PowerFactor("0.9").rounded(places, rounding=QuantityRounding.HALF_UP)


def test_power_factor_comparisons_are_exact() -> None:
    two_thirds = PowerFactor(Fraction(2, 3))
    assert two_thirds < PowerFactor("0.667")
    assert two_thirds > PowerFactor("0.666")
    assert two_thirds <= PowerFactor(Fraction(4, 6))
    assert two_thirds >= PowerFactor(Fraction(4, 6))
    assert two_thirds == PowerFactor(Fraction(4, 6))
    assert hash(two_thirds) == hash(PowerFactor(Fraction(4, 6)))
    assert PowerFactor("0.9") != Decimal("0.9")
    for op in ("__lt__", "__le__", "__gt__", "__ge__"):
        assert getattr(two_thirds, op)(0.5) is NotImplemented
    with pytest.raises(TypeError):
        _ = two_thirds < 0.5  # type: ignore[operator]
    assert repr(two_thirds) == "PowerFactor(2/3)"
