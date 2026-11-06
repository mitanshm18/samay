"""Property tests for bill recalculation, against an independent Fraction oracle.

The oracle below re-derives every line from the SAMAY-DEMO-1 definition using
Python Fractions and its own half-up rounding. It shares no code with the
engine beyond reading the inputs, so a mistake would have to be made twice,
in two different ways, to go unnoticed.
"""

from decimal import Decimal
from fractions import Fraction
from math import floor

from bills import SYN, VER, bill, entered, other
from hypothesis import given
from hypothesis import strategies as st

from samay.billing import LineBasis, ZoneConsumption, recompute_bill
from samay.core import ApparentEnergy, DataStatus, Money
from samay.tariffs import SAMAY_DEMO_1

# kVA and kVAh with 3 places, as integers of thousandths.
thousandths = st.integers(min_value=0, max_value=5 * 10**9)  # up to 5,000,000.000
demand = st.integers(min_value=1, max_value=10**7)  # 0.001 to 10,000.000 kVA
rupees = st.integers(min_value=-(10**7), max_value=10**7)  # printed lines, in paise


def half_up(x: Fraction) -> int:
    """Nearest integer, ties away from zero (the oracle's own rounding)."""
    if x >= 0:
        return floor(x + Fraction(1, 2))
    return -floor(-x + Fraction(1, 2))


def to_text(value: int) -> str:
    return str(Decimal(value).scaleb(-3))


def oracle(cd: int, md: int, peak: int, off: int, normal: int, others: list[int]) -> list[int]:
    """Every money line in paise, recomputed independently. Inputs in thousandths."""
    cd_f, md_f = Fraction(cd, 1000), Fraction(md, 1000)
    kvah = Fraction(peak + off + normal, 1000)
    billing_demand = max(md_f, cd_f * Fraction(75, 100))
    c2 = half_up(40000 * billing_demand)
    c3 = half_up(max(md_f - cd_f, Fraction(0)) * 40000 * Fraction(3, 2))
    c4 = half_up(900 * kvah)
    c5 = half_up(150 * Fraction(peak, 1000) - 100 * Fraction(off, 1000))
    c6 = half_up(Fraction(5, 100) * (c2 + c3 + c4 + c5))
    subtotal = c2 + c3 + c4 + c5 + c6 + sum(others)
    c9 = 100 * half_up(Fraction(subtotal, 100)) - subtotal
    return [c2, c3, c4, c5, c6, *others, c9]


@given(
    demand,
    demand,
    thousandths,
    thousandths,
    thousandths,
    st.lists(rupees, max_size=3),
    st.sampled_from(list(DataStatus)),
)
def test_engine_matches_independent_oracle(
    cd: int, md: int, peak: int, off: int, normal: int, others: list[int], status: DataStatus
) -> None:
    total_kvah = peak + off + normal
    b = bill(
        cd=to_text(cd),
        md=to_text(md),
        kwh="0",
        kvah=to_text(total_kvah),
        tod=ZoneConsumption(
            entered(ApparentEnergy(to_text(peak)), status),
            entered(ApparentEnergy(to_text(off)), status),
            entered(ApparentEnergy(to_text(normal)), status),
        ),
        printed=tuple(other(f"line {i}", str(Decimal(p).scaleb(-2))) for i, p in enumerate(others)),
        status=status,
    )
    result = recompute_bill(b, SAMAY_DEMO_1)
    expected = oracle(cd, md, peak, off, normal, others)
    got = [line.amount.value.paise for line in result.lines]
    assert got == expected

    # The total is the sum of all lines, rounded to a whole rupee.
    total = result.total.value
    assert total == Money(sum(got))
    assert total.paise % 100 == 0
    assert total == result.subtotal.value + result.rounding_off.amount.value
    assert abs(result.rounding_off.amount.value.paise) <= 50

    # Each recalculated line is within half a paisa of its exact amount (rounded once).
    for line in result.charges:
        if line.basis is LineBasis.RECALCULATED:
            assert line.exact is not None
            assert abs(Decimal(line.amount.value.paise) - line.exact.value.paise) <= Decimal("0.5")

    # Synthetic status: the tariff is synthetic, so the total always is.
    assert result.total.is_synthetic
    assert result.line(result.lines[0].code).amount.is_synthetic


@given(demand, demand, thousandths, thousandths)
def test_more_demand_or_energy_never_lowers_the_bill(
    cd: int, md: int, energy: int, extra: int
) -> None:
    def total(md_value: int, kvah: int) -> int:
        b = bill(
            cd=to_text(cd),
            md=to_text(md_value),
            kwh="0",
            kvah=to_text(kvah),
            tod=ZoneConsumption(
                entered(ApparentEnergy("0")),
                entered(ApparentEnergy("0")),
                entered(ApparentEnergy(to_text(kvah))),
            ),
        )
        return recompute_bill(b, SAMAY_DEMO_1).total.value.paise

    base = total(md, energy)
    assert total(md + extra % 10**7, energy) >= base
    assert total(md, energy + extra) >= base


@given(demand, demand)
def test_demand_charge_never_below_the_floor(cd: int, md: int) -> None:
    b = bill(cd=to_text(cd), md=to_text(md))
    result = recompute_bill(b, SAMAY_DEMO_1)
    floor_charge = Fraction(cd, 1000) * Fraction(75, 100) * 40000
    demand_line = result.lines[0].amount.value.paise
    assert demand_line >= half_up(floor_charge)
    assert (
        result.quantity("billing_demand").value.value >= result.quantity("demand_floor").value.value
    )


@given(st.integers(min_value=0, max_value=10**6), st.booleans())
def test_half_rupee_ties_round_away_from_zero(rupees_part: int, negative: bool) -> None:
    # Fixed part: CD 0.001 kVA, nothing else -> C2 = 40000 x 0.00075 = 30, duty 5% x 30
    # = 1.5 -> 2, so C2 + C6 = 32 paise. A printed line makes the subtotal exactly
    # +/-(100 x rupees_part + 50) paise: a half-rupee tie.
    target = 100 * rupees_part + 50
    subtotal = -target if negative else target
    printed = str(Decimal(subtotal - 32).scaleb(-2))
    b = bill(
        cd="0.001", md="0", kwh="0", kvah="0", tod=zones_zero(), printed=(other("x", printed),)
    )
    result = recompute_bill(b, SAMAY_DEMO_1)
    assert result.subtotal.value == Money(subtotal)
    away = target + 50
    assert result.total.value == Money(-away if negative else away)


def zones_zero() -> ZoneConsumption:
    zero = entered(ApparentEnergy("0"))
    return ZoneConsumption(zero, zero, zero)


@given(st.sampled_from([SYN, VER]))
def test_missing_zones_always_give_a_missing_total(status: DataStatus) -> None:
    result = recompute_bill(bill(zones=None, status=status), SAMAY_DEMO_1)
    assert result.total.is_missing
    assert result.total.is_synthetic  # the tariff is synthetic either way
