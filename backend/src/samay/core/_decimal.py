"""Exact decimal helpers shared by the core (internal module).

Isolation from Python's shared decimal context
----------------------------------------------
Python's decimal operators (+, -, abs(), unary minus, scaleb(), quantize()
without a context argument, ...) use the *thread's current context*, which any
code can change with decimal.getcontext().prec = 4 or decimal.localcontext().
If the core used those operators, such a change would silently round money.

Therefore every arithmetic operation in samay.core goes through one of the two
private contexts below, called as context methods (EXACT.add(a, b),
EXACT.minus(a), EXACT.abs(a), EXACT.scaleb(a, n), ...). Only operations that
are context-independent are used directly: the Decimal() constructor,
comparisons, as_tuple(), is_finite(), int() and Fraction(). The regression
tests in tests/core/test_decimal_context.py run the core under hostile global
contexts and require identical results.
"""

from decimal import (
    ROUND_HALF_EVEN,
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
# The settings are spelled out so they never depend on DefaultContext.
_PRECISION = 100
EXACT = Context(
    prec=_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[Inexact, InvalidOperation, DivisionByZero, Overflow],
)

# Used only by quantize() to apply an explicit rounding rule, so it must be
# allowed to round; the rounding mode is always passed in by the caller.
ROUNDING = Context(
    prec=_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

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
    if EXACT.abs(value) >= limit:
        raise InvalidValueError(f"{what}: {value} is outside the supported range (< {limit})")
