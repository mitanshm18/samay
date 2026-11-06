"""M1: any tariff that passes validation can calculate any valid bill exactly.

Hypothesis builds tariffs at and around the precision limits (demand rates
with 0-6 decimal places of paise, floor percentages with 0-2, multipliers
with 0-3). Either the tariff is refused when it is created, or every bill
calculates without a precision error, and its lines match an independent
Fraction calculation.
"""

import dataclasses
from decimal import Decimal
from fractions import Fraction
from math import floor

from bills import bill, zones
from hypothesis import assume, given
from hypothesis import strategies as st

from samay.billing import recompute_bill
from samay.core import Rate, RateBasis, Unit
from samay.tariffs import SAMAY_DEMO_1, Tariff, TariffError


def half_up(x: Fraction) -> int:
    return floor(x + Fraction(1, 2)) if x >= 0 else -floor(-x + Fraction(1, 2))


def scaled(digits: int, places: int) -> Decimal:
    return Decimal(digits).scaleb(-places)


@st.composite
def tariff_parts(draw: st.DrawFn) -> tuple[Decimal, Decimal, Decimal]:
    rate = scaled(draw(st.integers(1, 10**11)), draw(st.integers(0, 6)))
    floor_percent = scaled(draw(st.integers(0, 10**4)), draw(st.integers(0, 2)))
    multiplier = scaled(draw(st.integers(0, 10**5)), draw(st.integers(0, 3)))
    assume(rate < 10**9 and floor_percent <= 100 and multiplier <= 100)
    return rate, floor_percent, multiplier


@given(
    tariff_parts(),
    st.integers(1, 10**7),  # CD in thousandths of a kVA
    st.integers(0, 10**7),  # MD in thousandths of a kVA
)
def test_accepted_tariffs_never_fail_mid_bill(
    parts: tuple[Decimal, Decimal, Decimal], cd: int, md: int
) -> None:
    rate, floor_percent, multiplier = parts
    try:
        tariff: Tariff = dataclasses.replace(
            SAMAY_DEMO_1,
            demand_rate=Rate.paise_per(rate, Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD),
            demand_floor_percent=floor_percent,
            excess_demand_multiplier=multiplier,
        )
    except TariffError:
        return  # refused up front: allowed
    cd_text, md_text = str(Decimal(cd).scaleb(-3)), str(Decimal(md).scaleb(-3))
    result = recompute_bill(
        bill(cd=cd_text, md=md_text, kwh="0", kvah="0", tod=zones("0", "0", "0")), tariff
    )  # must not raise

    cd_f, md_f, rate_f = Fraction(cd, 1000), Fraction(md, 1000), Fraction(rate)
    billing_demand = max(md_f, cd_f * Fraction(floor_percent) / 100)
    expected_demand = half_up(rate_f * billing_demand)
    expected_excess = half_up(max(md_f - cd_f, Fraction(0)) * rate_f * Fraction(multiplier))
    got = [line.amount.value.paise for line in result.lines[:2]]
    assert got == [expected_demand, expected_excess]
