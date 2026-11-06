"""The only place in the core where rounding happens.

Every rounding is requested by name. There is no default rule: a caller that
turns an exact amount into Money must say how to round it.
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, Inexact
from enum import Enum

from ._decimal import EXACT, ROUNDING
from .errors import PrecisionError

_ONE = Decimal(1)


class RoundingRule(Enum):
    """How an exact amount of paise becomes a whole number of paise.

    HALF_UP rounds a tie away from zero (12.5 -> 13, -12.5 -> -13), which is
    Python's ROUND_HALF_UP. Which rule a real tariff uses must come from the
    tariff order; for the synthetic tariff, HALF_UP_PAISA is an assumption.
    """

    HALF_UP_PAISA = "half-up to the paisa"
    HALF_EVEN_PAISA = "half-even to the paisa"
    HALF_UP_RUPEE = "half-up to the rupee"
    CEIL_PAISA = "up to the next paisa"
    FLOOR_PAISA = "down to the previous paisa"

    @property
    def quantum_paise(self) -> int:
        """Step the result is a multiple of, in paise."""
        return 100 if self is RoundingRule.HALF_UP_RUPEE else 1

    @property
    def decimal_mode(self) -> str:
        """The decimal-module rounding constant for this rule."""
        return _MODES[self]


_MODES: dict[RoundingRule, str] = {
    RoundingRule.HALF_UP_PAISA: ROUND_HALF_UP,
    RoundingRule.HALF_EVEN_PAISA: ROUND_HALF_EVEN,
    RoundingRule.HALF_UP_RUPEE: ROUND_HALF_UP,
    RoundingRule.CEIL_PAISA: ROUND_CEILING,
    RoundingRule.FLOOR_PAISA: ROUND_FLOOR,
}


def round_paise(amount_paise: Decimal, rule: RoundingRule) -> int:
    """Round an exact amount of paise to a whole number of paise using rule."""
    if not isinstance(rule, RoundingRule):
        raise TypeError(f"rule must be a RoundingRule, got {type(rule).__name__}")
    if not isinstance(amount_paise, Decimal) or not amount_paise.is_finite():
        raise TypeError("amount_paise must be a finite Decimal")
    if amount_paise.adjusted() > 80:
        raise PrecisionError(f"{amount_paise} paise has too many digits to round exactly")
    try:
        # Exact division (scaling by 1 or 100). EXACT raises rather than round,
        # so the named rule below is the only rounding that ever happens.
        steps = EXACT.divide(amount_paise, Decimal(rule.quantum_paise))
    except Inexact:
        raise PrecisionError(f"{amount_paise} paise has too many digits to round exactly") from None
    whole = steps.quantize(_ONE, rounding=rule.decimal_mode, context=ROUNDING)
    return int(whole) * rule.quantum_paise


class QuantityRounding(Enum):
    """Explicit rounding for derived physical quantities (never applied implicitly)."""

    HALF_UP = ROUND_HALF_UP
    HALF_EVEN = ROUND_HALF_EVEN
