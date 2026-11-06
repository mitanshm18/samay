"""Rounding rules: every tie case is worked out by hand."""

from decimal import Decimal

import pytest

from samay.core import QuantityRounding, RoundingRule, round_paise

R = RoundingRule


@pytest.mark.parametrize(
    ("amount", "rule", "expected"),
    [
        # Exact half a paisa, positive.
        ("12.5", R.HALF_UP_PAISA, 13),
        ("12.5", R.HALF_EVEN_PAISA, 12),  # 12 is even
        ("13.5", R.HALF_EVEN_PAISA, 14),  # 14 is even
        ("12.5", R.CEIL_PAISA, 13),
        ("12.5", R.FLOOR_PAISA, 12),
        # Exact half a paisa, negative (credits): half-up rounds away from zero.
        ("-12.5", R.HALF_UP_PAISA, -13),
        ("-12.5", R.HALF_EVEN_PAISA, -12),
        ("-12.5", R.CEIL_PAISA, -12),
        ("-12.5", R.FLOOR_PAISA, -13),
        # Not a tie.
        ("12.4999", R.HALF_UP_PAISA, 12),
        ("12.5001", R.HALF_EVEN_PAISA, 13),
        ("12.0001", R.CEIL_PAISA, 13),
        ("12.9999", R.FLOOR_PAISA, 12),
        # Already whole: unchanged by every rule.
        ("100", R.HALF_UP_PAISA, 100),
        ("100", R.CEIL_PAISA, 100),
        ("-100", R.FLOOR_PAISA, -100),
        # To the rupee: ₹123.50 -> ₹124, ₹123.4999 -> ₹123, -₹123.50 -> -₹124.
        ("12350", R.HALF_UP_RUPEE, 12400),
        ("12349.99", R.HALF_UP_RUPEE, 12300),
        ("-12350", R.HALF_UP_RUPEE, -12400),
        ("0", R.HALF_UP_RUPEE, 0),
    ],
)
def test_rounding_table(amount: str, rule: RoundingRule, expected: int) -> None:
    assert round_paise(Decimal(amount), rule) == expected


def test_every_rule_has_quantum_and_mode() -> None:
    for rule in RoundingRule:
        assert rule.quantum_paise in (1, 100)
        assert isinstance(rule.decimal_mode, str)
        assert rule.value  # human-readable label


def test_rule_must_be_a_rounding_rule() -> None:
    with pytest.raises(TypeError, match="RoundingRule"):
        round_paise(Decimal("1.5"), "HALF_UP")  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", [1.5, Decimal("NaN"), Decimal("Infinity"), "1.5"])
def test_amount_must_be_finite_decimal(amount: object) -> None:
    with pytest.raises(TypeError):
        round_paise(amount, RoundingRule.HALF_UP_PAISA)  # type: ignore[arg-type]


def test_quantity_rounding_modes() -> None:
    assert {m.name for m in QuantityRounding} == {"HALF_UP", "HALF_EVEN"}
