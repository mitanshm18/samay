"""Property-based tests: invariants checked over thousands of generated cases."""

from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction

from hypothesis import assume, given
from hypothesis import strategies as st

from samay.core import (
    ApparentEnergy,
    DataStatus,
    Duration,
    Energy,
    ExactAmount,
    IntervalReading,
    MeterInterval,
    Money,
    Power,
    PowerFactor,
    PrecisionError,
    QuantityRounding,
    Rate,
    RoundingRule,
    Traced,
    Unit,
    average_power_factor,
    round_paise,
)

LIMIT = 10**15
paise = st.integers(min_value=-LIMIT, max_value=LIMIT)
money = paise.map(Money)
exact_paise = st.decimals(
    min_value=-(10**12), max_value=10**12, places=6, allow_nan=False, allow_infinity=False
)
quantity_value = st.decimals(
    min_value=0, max_value=10**9, places=3, allow_nan=False, allow_infinity=False
)
power_value = st.decimals(
    min_value=0, max_value=10**6, places=3, allow_nan=False, allow_infinity=False
)  # up to 1 GW
hours_value = st.decimals(
    min_value=0, max_value=10**5, places=3, allow_nan=False, allow_infinity=False
)  # up to ~11 years
rules = st.sampled_from(list(RoundingRule))


# ---- money ------------------------------------------------------------------


@given(money, money, money)
def test_addition_is_associative_and_commutative(a: Money, b: Money, c: Money) -> None:
    assert (a + b) + c == a + (b + c)
    assert a + b == b + a


@given(money, money)
def test_subtraction_undoes_addition(a: Money, b: Money) -> None:
    assert a + b - b == a
    assert a - a == Money.zero()
    assert (-a).__neg__() == a


@given(paise)
def test_rupee_round_trip_is_lossless(p: int) -> None:
    m = Money(p)
    assert Money.from_rupees(m.to_rupees()) == m
    assert Money.from_rupees(str(m.to_rupees())) == m


@given(money, st.lists(st.integers(min_value=0, max_value=10**6), min_size=1, max_size=12))
def test_allocate_sums_exactly_and_is_fair(total: Money, weights: list[int]) -> None:
    assume(sum(weights) > 0)
    parts = total.allocate(weights)
    assert len(parts) == len(weights)
    assert sum(parts, Money.zero()) == total
    weight_sum = sum(weights)
    for part, weight in zip(parts, weights, strict=True):
        fair = Fraction(total.paise * weight, weight_sum)
        assert abs(part.paise - fair) < 1
        if weight == 0:
            assert part == Money.zero()


@given(paise)
def test_format_round_trips(p: int) -> None:
    text = Money(p).format_inr()
    digits = text.replace("₹", "").replace(",", "")
    assert Money.from_rupees(digits) == Money(p)


# ---- rounding ---------------------------------------------------------------


@given(exact_paise, rules)
def test_rounding_moves_by_at_most_one_quantum(amount: Decimal, rule: RoundingRule) -> None:
    rounded = round_paise(amount, rule)
    step = rule.quantum_paise
    assert rounded % step == 0
    distance = abs(Decimal(rounded) - amount)
    if rule in (RoundingRule.CEIL_PAISA, RoundingRule.FLOOR_PAISA):
        assert distance < step
    else:
        assert distance <= Decimal(step) / 2


@given(exact_paise)
def test_ceil_and_floor_bracket_the_amount(amount: Decimal) -> None:
    assert round_paise(amount, RoundingRule.FLOOR_PAISA) <= amount
    assert round_paise(amount, RoundingRule.CEIL_PAISA) >= amount


@given(paise, rules)
def test_whole_paise_unchanged_by_paisa_rules(p: int, rule: RoundingRule) -> None:
    if rule.quantum_paise == 1:
        assert ExactAmount(Decimal(p)).round(rule) == Money(p)


@given(st.lists(exact_paise, min_size=1, max_size=10))
def test_exact_sum_rounded_once_is_within_half_paisa(amounts: list[Decimal]) -> None:
    total = sum((ExactAmount(a) for a in amounts), ExactAmount(Decimal(0)))
    assert total.paise == sum(amounts, Decimal(0))
    rounded = total.round(RoundingRule.HALF_UP_PAISA)
    assert abs(Decimal(rounded.paise) - total.paise) <= Decimal("0.5")


# ---- rates and quantities ---------------------------------------------------


@given(
    st.decimals(min_value=-1000, max_value=10**5, places=4, allow_nan=False, allow_infinity=False),
    quantity_value,
)
def test_rate_times_energy_is_exact(rupees: Decimal, kwh: Decimal) -> None:
    exact = Rate.rupees_per(rupees, Unit.KWH) * Energy(kwh)
    assert exact.paise == rupees * 100 * kwh  # Hypothesis decimals are small enough to be exact


@given(quantity_value, quantity_value)
def test_quantity_addition(a: Decimal, b: Decimal) -> None:
    total = Energy(a) + Energy(b)
    assert total.value == a + b
    assert total - Energy(b) == Energy(a)


@given(power_value, hours_value)
def test_power_times_duration_never_silently_rounds(kw: Decimal, hours: Decimal) -> None:
    exact = kw * hours
    try:
        energy = Power(kw) * Duration(hours)
    except PrecisionError:
        assert exact != exact.quantize(Decimal("0.001"))
        rounded = Power(kw).energy_over(Duration(hours), rounding=QuantityRounding.HALF_UP)
        assert abs(rounded.value - exact) <= Decimal("0.0005")
    else:
        assert energy.value == exact


# ---- power factor -----------------------------------------------------------


@given(quantity_value, quantity_value)
def test_power_factor_is_exact_ratio_in_range(a: Decimal, b: Decimal) -> None:
    kwh, kvah = sorted((a, b))
    assume(kvah > 0)

    interval = MeterInterval(
        "M1", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
    )
    pf = average_power_factor(
        IntervalReading(Energy(kwh), interval), IntervalReading(ApparentEnergy(kvah), interval)
    )
    assert pf.ratio == Fraction(kwh) / Fraction(kvah)
    assert PowerFactor(0) <= pf <= PowerFactor(1)
    for mode in QuantityRounding:
        assert abs(Fraction(pf.rounded(3, rounding=mode)) - pf.ratio) <= Fraction(1, 2000)


# ---- provenance -------------------------------------------------------------

statuses = st.sampled_from(list(DataStatus))


@given(st.lists(st.tuples(paise, statuses), min_size=1, max_size=8))
def test_synthetic_input_always_gives_synthetic_output(items: list[tuple[int, DataStatus]]) -> None:
    leaves = [Traced.entered(Money(p), by="test", status=s) for p, s in items]

    def total(*values: Money) -> Money:
        return sum(values, Money.zero())

    result = Traced.derive(total, *leaves, description="sum")
    expected = (
        DataStatus.SYNTHETIC
        if any(s is DataStatus.SYNTHETIC for _, s in items)
        else DataStatus.VERIFIED
    )
    assert result.status is expected
    assert result.value == Money(sum(p for p, _ in items))
