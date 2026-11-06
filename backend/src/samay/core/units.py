"""Electricity quantities that cannot be mixed by accident.

Each quantity type holds an exact Decimal in one base unit. Adding kWh to kVAh,
or comparing kW with kVA, raises UnitMismatchError. Values are never negative,
never floats, and never carry more than 3 decimal places (meter resolution):
excess precision is refused, not rounded.
"""

from __future__ import annotations

from decimal import Decimal, Inexact
from enum import Enum
from fractions import Fraction
from typing import ClassVar, NoReturn, Self

from ._decimal import (
    EXACT,
    ROUNDING,
    DecimalInput,
    check_magnitude,
    check_places,
    decimal_places,
    to_decimal,
)
from .errors import InvalidValueError, PrecisionError, UnitMismatchError
from .rounding import QuantityRounding

MAX_PLACES = 3
_MAGNITUDE_LIMIT = Decimal(10) ** 15
_THOUSAND = Decimal(1000)


class Unit(Enum):
    """Base unit of a quantity type."""

    KWH = "kWh"
    KVAH = "kVAh"
    KVARH = "kVArh"
    KW = "kW"
    KVA = "kVA"
    HOUR = "h"


class Quantity:
    """Base class for a non-negative physical quantity in a fixed base unit."""

    __slots__ = ("_value",)
    UNIT: ClassVar[Unit]

    def __init__(self, value: DecimalInput) -> None:
        what = f"{type(self).__name__} ({self.UNIT.value})"
        number = to_decimal(value, what=what)
        check_places(number, MAX_PLACES, what=what, hint="round it explicitly before creating it")
        check_magnitude(number, _MAGNITUDE_LIMIT, what=what)
        if number < 0:
            raise InvalidValueError(f"{what}: {number} is negative")
        self._value = number + 0  # normalises -0 to 0

    @property
    def value(self) -> Decimal:
        """The exact value in the base unit."""
        return self._value

    @classmethod
    def zero(cls) -> Self:
        return cls(0)

    def _require_same(self, other: object, operation: str) -> bool:
        """True if other has the same type; raise for another quantity type."""
        if type(other) is type(self):
            return True
        if isinstance(other, Quantity):
            raise UnitMismatchError(
                f"cannot {operation} {type(self).__name__} ({self.UNIT.value}) and "
                f"{type(other).__name__} ({other.UNIT.value})"
            )
        return False

    def __add__(self, other: Self) -> Self:
        if not self._require_same(other, "add"):
            return NotImplemented
        return type(self)(EXACT.add(self._value, other._value))

    def __sub__(self, other: Self) -> Self:
        if not self._require_same(other, "subtract"):
            return NotImplemented
        if other._value > self._value:
            raise InvalidValueError(
                f"{type(self).__name__}: {self._value} - {other._value} would be negative"
            )
        return type(self)(EXACT.subtract(self._value, other._value))

    def __truediv__(self, other: object) -> NoReturn:
        raise UnitMismatchError(
            f"{type(self).__name__} cannot be divided directly; for a power factor use "
            "average_power_factor() with two IntervalReading values for the same meter and interval"
        )

    def __lt__(self, other: Self) -> bool:
        if not self._require_same(other, "compare"):
            return NotImplemented
        return self._value < other._value

    def __le__(self, other: Self) -> bool:
        if not self._require_same(other, "compare"):
            return NotImplemented
        return self._value <= other._value

    def __gt__(self, other: Self) -> bool:
        if not self._require_same(other, "compare"):
            return NotImplemented
        return self._value > other._value

    def __ge__(self, other: Self) -> bool:
        if not self._require_same(other, "compare"):
            return NotImplemented
        return self._value >= other._value

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            assert isinstance(other, Quantity)
            return self._value == other._value
        if isinstance(other, Quantity):
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self), self._value))

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self._value}')"

    def __str__(self) -> str:
        return f"{self._value} {self.UNIT.value}"


def _from_thousandths(cls: type[Quantity], value: DecimalInput, name: str) -> Decimal:
    number = to_decimal(value, what=f"{cls.__name__}.{name}")
    return EXACT.multiply(number, _THOUSAND)


def _product[Q: Quantity](
    result: type[Q], a: Decimal, b: Decimal, rounding: QuantityRounding | None
) -> Q:
    exact = EXACT.multiply(a, b)
    if decimal_places(exact) > MAX_PLACES:
        if rounding is None:
            raise PrecisionError(
                f"{result.__name__}: {a} x {b} = {exact} is not exact at {MAX_PLACES} decimal "
                "places; use energy_over(duration, rounding=...) to round explicitly"
            )
        exact = exact.quantize(
            Decimal(1).scaleb(-MAX_PLACES), rounding=rounding.value, context=ROUNDING
        )
    return result(exact)


class Energy(Quantity):
    """Active energy in kWh."""

    __slots__ = ()
    UNIT = Unit.KWH

    @classmethod
    def from_mwh(cls, value: DecimalInput) -> Energy:
        return cls(_from_thousandths(cls, value, "from_mwh"))


class ApparentEnergy(Quantity):
    """Apparent energy in kVAh."""

    __slots__ = ()
    UNIT = Unit.KVAH

    @classmethod
    def from_mvah(cls, value: DecimalInput) -> ApparentEnergy:
        return cls(_from_thousandths(cls, value, "from_mvah"))


class ReactiveEnergy(Quantity):
    """Reactive energy in kVArh."""

    __slots__ = ()
    UNIT = Unit.KVARH


class Duration(Quantity):
    """A length of time in hours."""

    __slots__ = ()
    UNIT = Unit.HOUR

    @classmethod
    def from_minutes(cls, minutes: DecimalInput) -> Duration:
        number = to_decimal(minutes, what="Duration.from_minutes")
        try:
            hours = EXACT.divide(number, Decimal(60))
        except Inexact:
            hours = None
        if hours is None or decimal_places(hours) > MAX_PLACES:
            raise PrecisionError(
                f"Duration: {number} minutes is not a whole number of thousandths of an hour"
            )
        return cls(hours)


class Power(Quantity):
    """Active power (demand) in kW."""

    __slots__ = ()
    UNIT = Unit.KW

    @classmethod
    def from_mw(cls, value: DecimalInput) -> Power:
        return cls(_from_thousandths(cls, value, "from_mw"))

    def __mul__(self, other: Duration) -> Energy:
        if not isinstance(other, Duration):
            return NotImplemented
        return _product(Energy, self.value, other.value, None)

    __rmul__ = __mul__

    def energy_over(self, duration: Duration, *, rounding: QuantityRounding) -> Energy:
        """Energy over duration, rounded to 3 decimal places with an explicit rule."""
        if not isinstance(duration, Duration):
            raise UnitMismatchError("energy_over() needs a Duration")
        return _product(Energy, self.value, duration.value, rounding)


class ApparentPower(Quantity):
    """Apparent power (demand) in kVA."""

    __slots__ = ()
    UNIT = Unit.KVA

    def __mul__(self, other: Duration) -> ApparentEnergy:
        if not isinstance(other, Duration):
            return NotImplemented
        return _product(ApparentEnergy, self.value, other.value, None)

    __rmul__ = __mul__

    def energy_over(self, duration: Duration, *, rounding: QuantityRounding) -> ApparentEnergy:
        """Apparent energy over duration, rounded to 3 decimal places with an explicit rule."""
        if not isinstance(duration, Duration):
            raise UnitMismatchError("energy_over() needs a Duration")
        return _product(ApparentEnergy, self.value, duration.value, rounding)


class PowerFactor:
    """A power factor between 0 and 1, held as an exact fraction.

    It is never a percentage: 0.95, not 95. A power factor computed from
    readings stays exact (for example 2/3) until rounded() is called with an
    explicit rule, so threshold comparisons in tariffs are exact.
    """

    __slots__ = ("_ratio",)

    def __init__(self, value: DecimalInput | Fraction) -> None:
        if isinstance(value, Fraction):
            ratio = value
        else:
            ratio = Fraction(to_decimal(value, what="PowerFactor"))
        if not 0 <= ratio <= 1:
            raise InvalidValueError(
                f"PowerFactor: {value} is outside 0 to 1 (a power factor is not a percentage)"
            )
        self._ratio = ratio

    @property
    def ratio(self) -> Fraction:
        return self._ratio

    def rounded(self, places: int, *, rounding: QuantityRounding) -> Decimal:
        """The power factor as a Decimal with places digits, rounded explicitly."""
        if type(places) is not int or not 0 <= places <= 6:
            raise InvalidValueError("places must be an int from 0 to 6")
        scaled = self._ratio * 10**places
        whole, remainder = divmod(scaled.numerator, scaled.denominator)
        twice = 2 * remainder
        if twice > scaled.denominator or (
            twice == scaled.denominator and (rounding is QuantityRounding.HALF_UP or whole % 2 == 1)
        ):
            whole += 1
        return Decimal(whole).scaleb(-places)

    def _other(self, other: object) -> Fraction | None:
        return other._ratio if isinstance(other, PowerFactor) else None

    def __lt__(self, other: PowerFactor) -> bool:
        ratio = self._other(other)
        return NotImplemented if ratio is None else self._ratio < ratio

    def __le__(self, other: PowerFactor) -> bool:
        ratio = self._other(other)
        return NotImplemented if ratio is None else self._ratio <= ratio

    def __gt__(self, other: PowerFactor) -> bool:
        ratio = self._other(other)
        return NotImplemented if ratio is None else self._ratio > ratio

    def __ge__(self, other: PowerFactor) -> bool:
        ratio = self._other(other)
        return NotImplemented if ratio is None else self._ratio >= ratio

    def __eq__(self, other: object) -> bool:
        ratio = self._other(other)
        return NotImplemented if ratio is None else self._ratio == ratio

    def __hash__(self) -> int:
        return hash((PowerFactor, self._ratio))

    def __repr__(self) -> str:
        return f"PowerFactor({self._ratio})"
