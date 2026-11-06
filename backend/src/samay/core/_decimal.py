"""Exact decimal helpers shared by the core (internal module).

All arithmetic in the core uses EXACT, a decimal context with high precision
that raises instead of rounding. Rounding happens only in samay.core.rounding,
with a rule named by the caller.
"""

from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
)

from .errors import InvalidValueError, PrecisionError

# Precision far above any value the core accepts, so exact results always fit.
# Inexact is trapped: any operation that would have to round raises instead.
EXACT = Context(prec=100, traps=[Inexact, InvalidOperation, DivisionByZero, Overflow])

# Used only to apply an explicit rounding rule (quantize must be allowed to round).
ROUNDING = Context(prec=100, traps=[InvalidOperation, DivisionByZero, Overflow])

type DecimalInput = Decimal | int | str


def to_decimal(value: object, *, what: str) -> Decimal:
    """Convert a str, int or Decimal to a finite Decimal.

    Binary floats (and bools) are refused: most decimal amounts, such as 7.35,
    cannot be represented exactly as a float.
    """
    if isinstance(value, bool | float):
        raise TypeError(
            f"{what}: {type(value).__name__} is not accepted; pass a str, int or Decimal "
            "(binary floats cannot represent most decimal amounts exactly)"
        )
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation:
            raise InvalidValueError(f"{what}: {value!r} is not a number") from None
    else:
        raise TypeError(f"{what}: expected str, int or Decimal, got {type(value).__name__}")
    if not result.is_finite():
        raise InvalidValueError(f"{what}: {value!r} is not a finite number")
    return result


def decimal_places(value: Decimal) -> int:
    """Number of significant digits after the decimal point (trailing zeros ignored).

    Computed from the digit tuple so that no context rounding can interfere.
    """
    _sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)  # finite values only
    if exponent >= 0 or not any(digits):  # whole numbers, and zero written as 0.000000
        return 0
    significant = len(digits)
    while digits[significant - 1] == 0:  # stops: at least one digit is non-zero
        significant -= 1
    trailing_zeros = len(digits) - significant
    return max(0, -exponent - trailing_zeros)


def check_places(value: Decimal, max_places: int, *, what: str, hint: str = "") -> None:
    """Raise PrecisionError if value has more than max_places decimal places."""
    if decimal_places(value) > max_places:
        message = f"{what}: {value} has more than {max_places} decimal places"
        raise PrecisionError(f"{message}; {hint}" if hint else message)


def check_magnitude(value: Decimal, limit: Decimal, *, what: str) -> None:
    """Raise InvalidValueError if abs(value) >= limit."""
    if abs(value) >= limit:
        raise InvalidValueError(f"{what}: {value} is outside the supported range (< {limit})")
