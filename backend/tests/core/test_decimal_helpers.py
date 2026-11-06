"""Internal exact-decimal helpers."""

from decimal import Decimal

import pytest

from samay.core import Energy, Power
from samay.core._decimal import decimal_places


@pytest.mark.parametrize(
    ("text", "places"),
    [
        ("0", 0),
        ("0.000000", 0),  # regression: found by Hypothesis (0.000 kW x 0.000 h)
        ("-0.00", 0),
        ("100", 0),
        ("1E+3", 0),
        ("1.500", 1),
        ("0.125", 3),
        ("1.2300000", 2),
        ("1E-7", 7),
    ],
)
def test_decimal_places(text: str, places: int) -> None:
    assert decimal_places(Decimal(text)) == places


def test_zero_power_times_zero_duration() -> None:
    from samay.core import Duration

    assert Power("0.000") * Duration("0.000") == Energy("0")
