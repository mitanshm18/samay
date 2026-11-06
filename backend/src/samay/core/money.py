"""Money in integer paise, exact rates, and explicit rounding.

Money holds an int number of paise and never a float. A rate multiplied by a
quantity gives an ExactAmount, which becomes Money only through
ExactAmount.round(rule) with a RoundingRule named by the caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from ._decimal import EXACT, DecimalInput, check_magnitude, check_places, to_decimal
from .errors import InvalidValueError, UnitMismatchError
from .rounding import RoundingRule, round_paise
from .units import Quantity, Unit

MAX_ABS_PAISE = 10**18
_PAISE_LIMIT = Decimal(MAX_ABS_PAISE)
# ExactAmount precision: rates have at most 6 places in paise and quantities 3,
# so real products need at most 9; percentages add at most 8. 12 leaves headroom.
MAX_EXACT_PLACES = 12
_RATE_PLACES = 6  # decimal places allowed in paise per unit
_PERCENT_PLACES = 6
_HUNDRED = Decimal(100)


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """An amount of money as a whole number of paise (1 rupee = 100 paise)."""

    paise: int

    def __post_init__(self) -> None:
        if type(self.paise) is not int:
            raise TypeError(
                f"Money holds an int number of paise, got {type(self.paise).__name__}; "
                "use Money.from_rupees('7.35') or ExactAmount.round(rule)"
            )
        if abs(self.paise) >= MAX_ABS_PAISE:
            raise InvalidValueError(f"Money: {self.paise} paise is outside the supported range")

    @classmethod
    def from_paise(cls, paise: int) -> Money:
        return cls(paise)

    @classmethod
    def from_rupees(cls, rupees: DecimalInput) -> Money:
        """Exact conversion from rupees with at most 2 decimal places.

        More precise amounts are refused; compute an ExactAmount and call
        .round(rule) instead, so the rounding is visible.
        """
        number = to_decimal(rupees, what="Money.from_rupees")
        check_places(
            number,
            2,
            what="Money.from_rupees",
            hint="use ExactAmount.from_rupees(...).round(rule) to round explicitly",
        )
        paise = EXACT.multiply(number, _HUNDRED)
        check_magnitude(paise, _PAISE_LIMIT, what="Money.from_rupees")
        return cls(int(paise))

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.paise + other.paise)

    def __radd__(self, other: int) -> Money:
        # Lets sum() start from 0. Only the int 0 is accepted.
        if type(other) is int and other == 0:
            return self
        return NotImplemented

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.paise - other.paise)

    def __neg__(self) -> Money:
        return Money(-self.paise)

    def to_exact(self) -> ExactAmount:
        return ExactAmount(Decimal(self.paise))

    def to_rupees(self) -> Decimal:
        """Exact rupees with two decimal places, e.g. Decimal('735.00')."""
        return EXACT.scaleb(Decimal(self.paise), -2)

    def apply_percent(self, percent: DecimalInput, *, rule: RoundingRule) -> Money:
        """percent % of this amount, rounded with rule (e.g. 7.5 for 7.5%)."""
        number = to_decimal(percent, what="percent")
        check_places(number, _PERCENT_PLACES, what="percent")
        check_magnitude(number, Decimal("1E+6"), what="percent")
        exact = EXACT.divide(EXACT.multiply(Decimal(self.paise), number), _HUNDRED)
        return ExactAmount(exact).round(rule)

    def allocate(self, weights: Sequence[int]) -> tuple[Money, ...]:
        """Split into parts proportional to weights, adding up exactly to this amount.

        Uses the largest-remainder method: each part is within one paisa of its
        exact share, and leftover paise go to the largest remainders (earliest
        position first on ties).
        """
        if isinstance(weights, str | bytes) or not weights:
            raise InvalidValueError("allocate() needs at least one weight")
        for weight in weights:
            if type(weight) is not int or weight < 0:
                raise InvalidValueError(f"allocate() weights must be non-negative ints: {weight!r}")
        total_weight = sum(weights)
        if total_weight == 0:
            raise InvalidValueError("allocate() weights must not all be zero")
        sign = -1 if self.paise < 0 else 1
        amount = abs(self.paise)
        shares = [amount * w // total_weight for w in weights]
        remainders = [amount * w % total_weight for w in weights]
        leftover = amount - sum(shares)
        order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
        for i in order[:leftover]:
            shares[i] += 1
        return tuple(Money(sign * share) for share in shares)

    def format_inr(self) -> str:
        """Display with Indian digit grouping, e.g. '₹12,34,567.89'."""
        sign = "-" if self.paise < 0 else ""
        rupees, paise = divmod(abs(self.paise), 100)
        digits = str(rupees)
        if len(digits) > 3:
            head, tail = digits[:-3], digits[-3:]
            groups: list[str] = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            groups.insert(0, head)
            digits = ",".join([*groups, tail])
        return f"{sign}₹{digits}.{paise:02d}"

    def __str__(self) -> str:
        return self.format_inr()


@dataclass(frozen=True, slots=True)
class ExactAmount:
    """An exact, possibly fractional, number of paise. Not Money until rounded."""

    paise: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.paise, Decimal) or not self.paise.is_finite():
            raise TypeError("ExactAmount holds a finite Decimal number of paise")
        check_magnitude(self.paise, _PAISE_LIMIT, what="ExactAmount")
        check_places(self.paise, MAX_EXACT_PLACES, what="ExactAmount (paise)")

    @classmethod
    def from_rupees(cls, rupees: DecimalInput) -> ExactAmount:
        number = to_decimal(rupees, what="ExactAmount.from_rupees")
        check_magnitude(number, _PAISE_LIMIT, what="ExactAmount.from_rupees")
        return cls(EXACT.multiply(number, _HUNDRED))

    def __add__(self, other: ExactAmount) -> ExactAmount:
        if not isinstance(other, ExactAmount):
            return NotImplemented
        return ExactAmount(EXACT.add(self.paise, other.paise))

    def __sub__(self, other: ExactAmount) -> ExactAmount:
        if not isinstance(other, ExactAmount):
            return NotImplemented
        return ExactAmount(EXACT.subtract(self.paise, other.paise))

    def __neg__(self) -> ExactAmount:
        return ExactAmount(EXACT.minus(self.paise))

    def round(self, rule: RoundingRule) -> Money:
        """The only way to turn an exact amount into Money: with a named rule."""
        return Money(round_paise(self.paise, rule))


@dataclass(frozen=True, slots=True)
class Rate:
    """An exact price in paise per unit of one quantity type, e.g. 735.5 paise/kWh."""

    paise_per_unit: Decimal
    unit: Unit

    def __post_init__(self) -> None:
        if not isinstance(self.paise_per_unit, Decimal) or not self.paise_per_unit.is_finite():
            raise TypeError("Rate.paise_per_unit must be a finite Decimal; use Rate.rupees_per()")
        if not isinstance(self.unit, Unit):
            raise TypeError("Rate.unit must be a Unit")
        check_places(self.paise_per_unit, _RATE_PLACES, what="Rate (paise per unit)")
        check_magnitude(self.paise_per_unit, Decimal("1E+9"), what="Rate (paise per unit)")

    @classmethod
    def rupees_per(cls, rupees: DecimalInput, unit: Unit) -> Rate:
        """E.g. Rate.rupees_per('7.355', Unit.KWH) for ₹7.355 per kWh."""
        number = to_decimal(rupees, what="Rate.rupees_per")
        check_magnitude(number, Decimal("1E+7"), what="Rate.rupees_per")
        return cls(EXACT.multiply(number, _HUNDRED), unit)

    @classmethod
    def paise_per(cls, paise: DecimalInput, unit: Unit) -> Rate:
        return cls(to_decimal(paise, what="Rate.paise_per"), unit)

    def __mul__(self, quantity: Quantity) -> ExactAmount:
        if not isinstance(quantity, Quantity):
            return NotImplemented
        if quantity.UNIT is not self.unit:
            raise UnitMismatchError(
                f"a rate per {self.unit.value} cannot be applied to "
                f"{type(quantity).__name__} ({quantity.UNIT.value})"
            )
        return ExactAmount(EXACT.multiply(self.paise_per_unit, quantity.value))

    __rmul__ = __mul__

    def __str__(self) -> str:
        return f"{self.paise_per_unit} paise/{self.unit.value}"
