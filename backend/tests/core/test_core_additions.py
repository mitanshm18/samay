"""Step 3A core additions: exact demand, rate basis, formatting, R1 and provenance items."""

from decimal import Decimal, InvalidOperation

import pytest

from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    Energy,
    ExactAmount,
    ExactApparentPower,
    InvalidValueError,
    Money,
    PrecisionError,
    Rate,
    RateBasis,
    RoundingRule,
    SamayCoreError,
    Traced,
    Unit,
    UnitMismatchError,
    format_rupees,
    round_paise,
)

SYN = DataStatus.SYNTHETIC
VER = DataStatus.VERIFIED


# ---- ExactApparentPower -----------------------------------------------------


def test_percent_of_demand_is_exact() -> None:
    # 100.123 kVA x 75% = 75.09225 kVA: 5 places, kept exactly, not rounded to 3.
    floor = ApparentPower("100.123").percent(75)
    assert floor.value == Decimal("75.09225")
    assert str(floor) == "75.09225 kVA"
    assert repr(floor) == "ExactApparentPower('75.09225')"
    # 2-place percentages are allowed: 500 x 62.5% = 312.5.
    assert ApparentPower("500").percent("62.5").value == Decimal("312.5")


def test_percent_rejects_bad_input() -> None:
    with pytest.raises(PrecisionError):
        ApparentPower("100").percent("75.125")
    with pytest.raises(InvalidValueError):
        ApparentPower("100").percent("-1")
    with pytest.raises(InvalidValueError):
        ApparentPower("100").percent("1000.01")
    with pytest.raises(TypeError):
        ApparentPower("100").percent(0.75)  # type: ignore[arg-type]


def test_exact_demand_compares_with_measured_demand() -> None:
    floor = ApparentPower("100.123").percent(75)  # 75.09225
    assert floor > ApparentPower("75.092")
    assert floor < ApparentPower("75.093")
    assert floor >= ExactApparentPower(Decimal("75.09225"))
    assert floor <= ExactApparentPower(Decimal("75.09225"))
    assert floor == ExactApparentPower(Decimal("75.09225"))
    assert floor != ApparentPower("75.092")
    assert ExactApparentPower.from_measured(ApparentPower("10")) == ExactApparentPower(Decimal(10))
    assert len({floor, ExactApparentPower(Decimal("75.092250"))}) == 1


def test_exact_demand_does_not_mix_with_other_units() -> None:
    floor = ApparentPower("100").percent(75)
    with pytest.raises(UnitMismatchError):
        _ = floor < ApparentEnergy("10")  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = floor < 5  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = floor > 5  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = floor <= 5  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = floor >= 5  # type: ignore[operator]
    with pytest.raises(UnitMismatchError):
        ExactApparentPower.from_measured(ApparentEnergy("1"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (Decimal("1.0000000001"), PrecisionError),
        (Decimal(-1), InvalidValueError),
        (Decimal("1e15"), InvalidValueError),
        (Decimal("NaN"), TypeError),
        ("1", TypeError),
    ],
)
def test_exact_demand_validation(value: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        ExactApparentPower(value)  # type: ignore[arg-type]


def test_rate_times_exact_demand() -> None:
    # ₹400/kVA = 40000 paise/kVA; 40000 x 75.09225 = 3,003,690 paise exactly.
    rate = Rate.rupees_per("400", Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD)
    assert rate * ApparentPower("100.123").percent(75) == ExactAmount(Decimal(3003690))
    with pytest.raises(UnitMismatchError):
        Rate.rupees_per("9", Unit.KVAH) * ExactApparentPower(Decimal(1))


# ---- rates ------------------------------------------------------------------


def test_rate_basis_defaults_and_display() -> None:
    assert Rate.rupees_per("9", Unit.KVAH).basis is RateBasis.PER_UNIT
    demand = Rate.paise_per("40000", Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD)
    assert demand.format_inr() == "₹400.00/kVA per billing period"
    assert str(demand) == "40000 paise/kVA per billing period"
    assert Rate.rupees_per("7.355", Unit.KWH).format_inr() == "₹7.355/kWh"
    assert Rate.rupees_per("-1.00", Unit.KVAH).format_inr() == "-₹1.00/kVAh"
    with pytest.raises(TypeError):
        Rate(Decimal(1), Unit.KWH, "per unit")  # type: ignore[arg-type]


def test_rate_scaled_is_exact_and_keeps_basis() -> None:
    # 40000 x 1.5 = 60000 paise/kVA, still per billing period.
    demand = Rate.rupees_per("400", Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD)
    scaled = demand.scaled("1.5")
    assert scaled.paise_per_unit == Decimal(60000)
    assert scaled.basis is RateBasis.PER_UNIT_PER_BILLING_PERIOD
    with pytest.raises(InvalidValueError):
        demand.scaled("1e3")
    with pytest.raises(PrecisionError):
        Rate.paise_per("0.000001", Unit.KWH).scaled("0.5")


# ---- money ------------------------------------------------------------------


def test_percent_exact_then_round() -> None:
    # ₹333.33 x 7.5% = 2499.975 paise exactly.
    assert Money(33333).percent_exact("7.5") == ExactAmount(Decimal("2499.975"))


@pytest.mark.parametrize(
    ("rupees", "text"),
    [
        (Decimal("90451.107"), "₹90,451.107"),
        (Decimal("1.5000"), "₹1.50"),
        (Decimal("0"), "₹0.00"),
        (Decimal("-0.0085"), "-₹0.0085"),
        (Decimal("-0"), "₹0.00"),
        (Decimal("1234567"), "₹12,34,567.00"),
    ],
)
def test_format_rupees_never_rounds(rupees: Decimal, text: str) -> None:
    assert format_rupees(rupees) == text


def test_format_rupees_rejects_non_decimals() -> None:
    with pytest.raises(TypeError):
        format_rupees(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        format_rupees(Decimal("Infinity"))


def test_exact_amount_format() -> None:
    assert ExactAmount(Decimal("9045110.7")).format_inr() == "₹90,451.107"


# ---- R1: absurd inputs raise SAMAY errors, never raw decimal errors ---------


@pytest.mark.parametrize(
    "value",
    ["1e999999999", "1e-999999999", "1" * 41, "0." + "0" * 40 + "1", "1e41"],
)
def test_absurd_inputs_raise_samay_errors(value: str) -> None:
    for make in (Money.from_rupees, ExactAmount.from_rupees, Energy):
        with pytest.raises(SamayCoreError):
            make(value)


def test_absurd_exact_amount_raises_precision_error() -> None:
    with pytest.raises(PrecisionError):
        ExactAmount(Decimal("1e-999999999"))
    with pytest.raises(InvalidValueError):
        ExactAmount(Decimal("1e999999999"))


def test_huge_rupees_checked_before_multiplying() -> None:
    with pytest.raises(InvalidValueError, match="outside"):
        Money.from_rupees("9" * 40)


def test_round_paise_rejects_huge_values_cleanly() -> None:
    with pytest.raises(PrecisionError, match="too many digits"):
        round_paise(Decimal("1e81"), RoundingRule.HALF_UP_RUPEE)


def test_no_invalid_operation_escapes() -> None:
    try:
        Money.from_rupees("1e99999999999")
    except InvalidOperation:  # pragma: no cover - this is the failure being guarded
        pytest.fail("raw decimal error escaped")
    except SamayCoreError:
        pass


# ---- provenance backlog items ----------------------------------------------


def _add(a: Money, b: Money) -> Money:
    return a + b


def test_derive_names_every_missing_input() -> None:
    a = Traced.missing(reason="kVAh not printed", status=SYN, kind=Money)
    b = Traced.missing(reason="MD not printed", status=VER, kind=Money)
    result = Traced.derive(_add, a, b, description="sum")
    assert result.note == "sum: missing inputs (kVAh not printed; MD not printed)"
    assert result.missing_reasons() == ("kVAh not printed", "MD not printed")
    later = Traced.derive(
        _add, result, Traced.entered(Money(1), by="x", status=VER), description="t"
    )
    assert later.missing_reasons() == ("kVAh not printed", "MD not printed")
    assert Traced.entered(Money(1), by="x", status=VER).missing_reasons() == ()


def test_estimate_spreads_to_derived_values() -> None:
    estimate = Traced.estimated(Money(5), basis="last month", status=VER)
    entered = Traced.entered(Money(1), by="x", status=VER)
    assert estimate.rests_on_estimate
    assert not entered.rests_on_estimate
    assert Traced.derive(_add, estimate, entered, description="sum").rests_on_estimate
    assert not Traced.derive(_add, entered, entered, description="sum").rests_on_estimate


# ---- backlog #5: rounding ties and symmetry ------------------------------------

from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402


@given(st.integers(min_value=-(10**15), max_value=10**15))
def test_paisa_ties_tell_half_up_from_half_even(n: int) -> None:
    tie = Decimal(n) + Decimal("0.5")  # exactly halfway between n and n + 1
    up = round_paise(tie, RoundingRule.HALF_UP_PAISA)
    even = round_paise(tie, RoundingRule.HALF_EVEN_PAISA)
    assert up == (n + 1 if tie > 0 else n)  # away from zero
    assert even == (n if n % 2 == 0 else n + 1)
    assert even % 2 == 0


@given(
    st.decimals(min_value=0, max_value=10**12, places=6, allow_nan=False, allow_infinity=False),
    st.sampled_from(
        [RoundingRule.HALF_UP_PAISA, RoundingRule.HALF_EVEN_PAISA, RoundingRule.HALF_UP_RUPEE]
    ),
)
def test_half_rules_are_symmetric(amount: Decimal, rule: RoundingRule) -> None:
    assert round_paise(-amount, rule) == -round_paise(amount, rule)


@given(
    st.decimals(
        min_value=-(10**9), max_value=10**9, places=6, allow_nan=False, allow_infinity=False
    ),
    st.decimals(min_value=0, max_value=10**9, places=6, allow_nan=False, allow_infinity=False),
    st.sampled_from(list(RoundingRule)),
)
def test_rounding_is_monotonic(a: Decimal, step: Decimal, rule: RoundingRule) -> None:
    assert round_paise(a, rule) <= round_paise(a + step, rule)
