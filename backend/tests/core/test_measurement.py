"""Power factor only from matching meter, interval and data."""

from datetime import UTC, datetime, timedelta, timezone
from fractions import Fraction

import pytest

from samay.core import (
    ApparentEnergy,
    Energy,
    IntervalMismatchError,
    IntervalReading,
    InvalidValueError,
    MeterInterval,
    PowerFactor,
    QuantityRounding,
    UnitMismatchError,
    average_power_factor,
)

IST = timezone(timedelta(hours=5, minutes=30), "IST")
START = datetime(2026, 10, 1, 0, 0, tzinfo=IST)
END = datetime(2026, 11, 1, 0, 0, tzinfo=IST)
OCTOBER = MeterInterval("HT-001", START, END)


def kwh(value: str, interval: MeterInterval = OCTOBER) -> IntervalReading[Energy]:
    return IntervalReading(Energy(value), interval)


def kvah(value: str, interval: MeterInterval = OCTOBER) -> IntervalReading[ApparentEnergy]:
    return IntervalReading(ApparentEnergy(value), interval)


def test_matching_readings_give_exact_power_factor() -> None:
    # 900 kWh / 1000 kVAh = 9/10.
    assert average_power_factor(kwh("900"), kvah("1000")) == PowerFactor("0.9")


def test_non_terminating_power_factor_stays_exact() -> None:
    # 2000 / 3000 = 2/3 exactly; rounding is a separate, explicit step.
    pf = average_power_factor(kwh("2000"), kvah("3000"))
    assert pf.ratio == Fraction(2, 3)
    assert str(pf.rounded(3, rounding=QuantityRounding.HALF_UP)) == "0.667"


def test_unity_and_zero_power_factor() -> None:
    assert average_power_factor(kwh("10"), kvah("10")) == PowerFactor(1)
    assert average_power_factor(kwh("0"), kvah("10")) == PowerFactor(0)


def test_same_instants_in_other_time_zone_match() -> None:
    utc = MeterInterval("HT-001", START.astimezone(UTC), END.astimezone(UTC))
    assert average_power_factor(kwh("900"), kvah("1000", utc)) == PowerFactor("0.9")


@pytest.mark.parametrize(
    "other",
    [
        MeterInterval("HT-002", START, END),  # different meter
        MeterInterval("HT-001", START, END - timedelta(days=1)),  # different end
        MeterInterval("HT-001", START + timedelta(minutes=15), END),  # different start
    ],
)
def test_mismatched_meter_or_interval_refused(other: MeterInterval) -> None:
    with pytest.raises(IntervalMismatchError, match="same meter and interval"):
        average_power_factor(kwh("900"), kvah("1000", other))


def test_more_active_than_apparent_is_inconsistent() -> None:
    with pytest.raises(InvalidValueError, match="exceeds"):
        average_power_factor(kwh("1001"), kvah("1000"))


def test_zero_apparent_energy_refused() -> None:
    with pytest.raises(InvalidValueError, match="undefined"):
        average_power_factor(kwh("0"), kvah("0"))


def test_swapped_or_wrong_quantities_refused() -> None:
    with pytest.raises(UnitMismatchError, match="active reading"):
        average_power_factor(kvah("1000"), kvah("1000"))  # type: ignore[arg-type]
    with pytest.raises(UnitMismatchError, match="apparent reading"):
        average_power_factor(kwh("900"), kwh("1000"))  # type: ignore[arg-type]


def test_interval_validation() -> None:
    naive = datetime(2026, 10, 1)
    with pytest.raises(InvalidValueError, match="timezone-aware"):
        MeterInterval("HT-001", naive, END)
    with pytest.raises(InvalidValueError, match="timezone-aware"):
        MeterInterval("HT-001", START, datetime(2026, 11, 1))
    with pytest.raises(InvalidValueError, match="after start"):
        MeterInterval("HT-001", END, START)
    with pytest.raises(InvalidValueError, match="after start"):
        MeterInterval("HT-001", START, START)
    with pytest.raises(InvalidValueError, match="meter_id"):
        MeterInterval("  ", START, END)
    with pytest.raises(InvalidValueError, match="meter_id"):
        MeterInterval(1, START, END)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="datetime"):
        MeterInterval("HT-001", "2026-10-01", END)  # type: ignore[arg-type]


def test_reading_validation() -> None:
    with pytest.raises(TypeError, match="Quantity"):
        IntervalReading("900", OCTOBER)  # type: ignore[type-var]
    with pytest.raises(TypeError, match="MeterInterval"):
        IntervalReading(Energy("900"), (START, END))  # type: ignore[arg-type]


def test_interval_str() -> None:
    assert str(OCTOBER) == "HT-001 [2026-10-01T00:00:00+05:30 .. 2026-11-01T00:00:00+05:30)"
