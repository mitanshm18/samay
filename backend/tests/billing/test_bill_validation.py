"""Bill input checks: errors stop the calculation, warnings travel with the result."""

from datetime import datetime
from typing import Any

import pytest
from bills import IST, VER, bill, entered, other, zones

from samay.billing import (
    BillInput,
    PrintedLine,
    Severity,
    ValidationIssue,
    ZoneConsumption,
    validate_bill,
)
from samay.core import ApparentEnergy, ApparentPower, Energy, MeterInterval, Money, Traced
from samay.tariffs import SAMAY_DEMO_1, ComponentCode


def codes(b: BillInput, severity: Severity | None = None) -> list[str]:
    return [
        i.code for i in validate_bill(b, SAMAY_DEMO_1) if severity is None or i.severity is severity
    ]


def errors(b: BillInput) -> list[str]:
    return codes(b, Severity.ERROR)


def test_clean_bill_has_only_the_synthetic_warning() -> None:
    assert codes(bill()) == ["synthetic-tariff"]


def test_kwh_above_kvah() -> None:
    assert errors(bill(kwh="100000.001")) == ["kwh-above-kvah"]
    assert errors(bill(kwh="100000")) == []  # equal is allowed (power factor 1)


def test_zero_contract_demand() -> None:
    assert errors(bill(cd="0")) == ["contract-demand-zero"]


def test_zones_must_add_up_to_total() -> None:
    # 25,000 + 30,000 + 45,000.001 = 100,000.001, not 100,000.
    assert errors(bill(tod=zones("25000", "30000", "45000.001"))) == ["tod-zones-sum"]
    assert errors(bill(tod=zones("25000", "30000", "44999.999"))) == ["tod-zones-sum"]


def test_partial_zones_cannot_already_exceed_total() -> None:
    partial = ZoneConsumption(
        entered(ApparentEnergy("60000")),
        entered(ApparentEnergy("40000.001")),
        Traced.missing(reason="normal zone not printed", status=VER, kind=ApparentEnergy),
    )
    assert errors(bill(tod=partial)) == ["tod-zones-exceed"]
    fits = ZoneConsumption(
        entered(ApparentEnergy("60000")),
        entered(ApparentEnergy("40000")),
        Traced.missing(reason="normal zone not printed", status=VER, kind=ApparentEnergy),
    )
    assert errors(bill(tod=fits)) == []
    assert "tod-zones-partial" in codes(bill(tod=fits))


def test_zones_unchecked_when_kvah_missing() -> None:
    missing = Traced.missing(reason="kVAh unreadable", status=VER, kind=ApparentEnergy)
    found = codes(bill(kvah=missing))
    assert "tod-zones-unchecked" in found
    assert "input-missing" in found


def test_duplicate_printed_codes() -> None:
    energy = PrintedLine(ComponentCode.ENERGY_CHARGE, "Energy", entered(Money(1)))
    assert errors(bill(printed=(energy, energy))) == ["duplicate-printed-code"]
    assert errors(bill(printed=(other("a", "1"), other("b", "2")))) == []


@pytest.mark.parametrize(
    ("start_day", "end_day", "unusual"),
    [(1, 29, False), (1, 28, True), (1, 31, False)],
)
def test_period_length(start_day: int, end_day: int, unusual: bool) -> None:
    # 1 to 29 March = 28 days, 1 to 28 = 27 days, 1 to 31 = 30 days.
    period = MeterInterval(
        "M1", datetime(2026, 3, start_day, tzinfo=IST), datetime(2026, 3, end_day, tzinfo=IST)
    )
    assert ("unusual-period" in codes(bill(period=period))) is unusual


def test_period_over_31_days() -> None:
    period = MeterInterval("M1", datetime(2026, 3, 1, tzinfo=IST), datetime(2026, 4, 2, tzinfo=IST))
    assert "unusual-period" in codes(bill(period=period))


def test_errors_sort_first_and_print_clearly() -> None:
    issues = validate_bill(bill(kwh="100000.001", cd="0"), SAMAY_DEMO_1)
    assert [i.severity for i in issues][:2] == [Severity.ERROR, Severity.ERROR]
    assert str(issues[-1]).startswith("warning: ")
    assert str(ValidationIssue(Severity.ERROR, "x", "bad")) == "error: bad [x]"


def test_validate_needs_the_right_types() -> None:
    with pytest.raises(TypeError):
        validate_bill("bill", SAMAY_DEMO_1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        validate_bill(bill(), "SAMAY-DEMO-1")  # type: ignore[arg-type]


# ---- input types --------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"bill_id": " "},
        {"period": "April"},
        {"contract_demand": ApparentPower("500")},  # not traced
        {"recorded_md": entered(Energy("1"))},  # wrong quantity
        {"kwh": entered(ApparentEnergy("1"))},
        {"kvah": entered(Energy("1"))},
        {"zones": {"peak": "1"}},
        {"printed_lines": [other("a", "1")]},
        {"printed_lines": ("a",)},
        {"printed_total": entered(ApparentEnergy("1"))},
    ],
)
def test_bill_input_types(changes: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        bill(**changes)


def test_part_types() -> None:
    with pytest.raises(TypeError):
        ZoneConsumption(
            entered(Energy("1")), entered(ApparentEnergy("1")), entered(ApparentEnergy("1"))
        )
    with pytest.raises(TypeError):
        PrintedLine("other", "x", entered(Money(1)))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        PrintedLine(ComponentCode.OTHER, "", entered(Money(1)))
    with pytest.raises(TypeError):
        PrintedLine(ComponentCode.OTHER, "x", entered(1))


def test_printed_total_is_kept_for_later() -> None:
    b = bill(printed_total=entered(Money(112_606_000)))
    assert b.printed_total is not None
    assert b.printed_total.value == Money(112_606_000)
