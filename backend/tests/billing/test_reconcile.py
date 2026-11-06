"""Reconciliation: printed minus calculated, in paise, zero tolerance (decision 0004).

Calculated amounts used below come from worked example A (hand-checked in 3A):
demand 16,493,800; excess 0; energy 90,000,000; ToD 750,000; duty 5,362,190;
rounding off +10; total 112,606,000 paise.
"""

import copy
import dataclasses

import pytest
from bills import SYN, VER, bill, entered, other
from hypothesis import given
from hypothesis import strategies as st

from samay.billing import (
    BillInput,
    ExplanationState,
    LineStatus,
    PrintedLine,
    ReconciliationInputError,
    ReconciliationReport,
    ZoneConsumption,
    recompute_bill,
    reconcile,
)
from samay.core import ApparentEnergy, DataStatus, Money, Provenance, Traced
from samay.tariffs import SAMAY_DEMO_1, ComponentCode

C = ComponentCode
EXAMPLE_A = {
    C.DEMAND_CHARGE: 16_493_800,
    C.EXCESS_DEMAND_CHARGE: 0,
    C.ENERGY_CHARGE: 90_000_000,
    C.TOD_ADJUSTMENT: 750_000,
    C.ELECTRICITY_DUTY: 5_362_190,
    C.ROUNDING_OFF: 10,
}
TOTAL_A = 112_606_000


def printed(code: ComponentCode, paise: int, status: object = VER) -> PrintedLine:
    return PrintedLine(code, code.value, entered(Money(paise), status))  # type: ignore[arg-type]


def all_printed(**changes: int) -> tuple[PrintedLine, ...]:
    amounts = dict(EXAMPLE_A)
    for name, paise in changes.items():
        amounts[C(name)] = paise
    return tuple(printed(code, paise) for code, paise in amounts.items())


def run(b: BillInput) -> ReconciliationReport:
    return reconcile(b, recompute_bill(b, SAMAY_DEMO_1))


def status_of(report: ReconciliationReport, code: ComponentCode) -> LineStatus:
    (line,) = [c for c in report.lines if c.code is code]
    return line.status


def diff_of(report: ReconciliationReport, code: ComponentCode) -> Traced[Money]:
    (line,) = [c for c in report.lines if c.code is code]
    return line.difference


# ---- MATCH and DIFFERS ------------------------------------------------------------


def test_everything_matches() -> None:
    report = run(bill(printed=all_printed(), printed_total=entered(Money(TOTAL_A))))
    assert all(c.status is LineStatus.MATCH for c in report.lines)
    assert len(report.matches) == 6
    assert report.explanation.state is ExplanationState.COMPLETE
    assert report.total.difference.value == Money(0)
    assert report.total.residual.value == Money(0)
    assert report.is_clean


def test_one_paisa_is_a_difference() -> None:
    # Printed energy 90,000,001 vs 90,000,000: +1 paisa, printed minus calculated.
    report = run(
        bill(printed=all_printed(energy_charge=90_000_001), printed_total=entered(Money(TOTAL_A)))
    )
    assert status_of(report, C.ENERGY_CHARGE) is LineStatus.DIFFERS
    assert diff_of(report, C.ENERGY_CHARGE).value == Money(1)
    assert diff_of(report, C.ENERGY_CHARGE).provenance is Provenance.CALCULATED
    # The total matches, yet a line differs: neither result implies the other.
    assert report.total.difference.value == Money(0)
    assert report.total.residual.value == Money(-1)  # 112,606,000 - 112,606,001
    assert report.explanation.state is ExplanationState.COMPLETE
    assert report.explanation.compared_difference.value == Money(1)
    assert not report.is_clean


def test_negative_difference_is_printed_minus_calculated() -> None:
    report = run(bill(printed=all_printed(demand_charge=16_493_700)))
    assert diff_of(report, C.DEMAND_CHARGE).value == Money(-100)


def test_offsetting_line_errors_still_reported() -> None:
    # +500 on energy and -500 on demand: the total agrees but two lines differ.
    report = run(
        bill(
            printed=all_printed(energy_charge=90_000_500, demand_charge=16_493_300),
            printed_total=entered(Money(TOTAL_A)),
        )
    )
    assert report.total.difference.value == Money(0)
    assert report.total.residual.value == Money(0)
    assert [c.code for c in report.differences] == [C.DEMAND_CHARGE, C.ENERGY_CHARGE]
    assert not report.is_clean


def test_all_lines_match_but_printed_total_differs() -> None:
    report = run(bill(printed=all_printed(), printed_total=entered(Money(TOTAL_A + 100))))
    assert len(report.matches) == 6
    assert report.total.difference.value == Money(100)
    assert report.total.residual.value == Money(100)  # the printed bill does not add up
    assert not report.is_clean


# ---- CALCULATED_ONLY (D1) -------------------------------------------------------------


def test_absent_zero_line_is_calculated_only_and_undetermined() -> None:
    lines = tuple(p for p in all_printed() if p.code is not C.EXCESS_DEMAND_CHARGE)
    report = run(bill(printed=lines, printed_total=entered(Money(TOTAL_A))))
    assert status_of(report, C.EXCESS_DEMAND_CHARGE) is LineStatus.CALCULATED_ONLY
    difference = diff_of(report, C.EXCESS_DEMAND_CHARGE)
    assert difference.is_missing  # never -0, never 0
    assert difference.note == "line not on printed bill"
    assert report.explanation.state is ExplanationState.PARTIAL
    assert len(report.matches) == 5  # not counted as a match even though SAMAY says ₹0
    assert report.total.difference.value == Money(0)  # total is still compared
    assert not report.is_clean


def test_absent_nonzero_line_is_calculated_only() -> None:
    lines = tuple(p for p in all_printed() if p.code is not C.ENERGY_CHARGE)
    report = run(bill(printed=lines))
    assert status_of(report, C.ENERGY_CHARGE) is LineStatus.CALCULATED_ONLY
    assert diff_of(report, C.ENERGY_CHARGE).is_missing


def test_no_printed_lines_at_all() -> None:
    report = run(bill())
    assert all(c.status is LineStatus.CALCULATED_ONLY for c in report.lines)
    assert report.explanation.state is ExplanationState.UNDETERMINABLE
    assert report.explanation.compared_difference.is_missing
    assert report.total.printed is None
    assert report.total.difference.is_missing
    assert "no printed total was given" in report.total.difference.note
    assert report.total.residual.is_missing


def test_printed_total_without_lines_has_no_residual() -> None:
    report = run(bill(printed_total=entered(Money(TOTAL_A))))
    assert report.total.difference.value == Money(0)
    assert report.total.residual.is_missing
    assert report.total.residual.note == "no printed lines were given"


# ---- CANNOT_COMPARE ----------------------------------------------------------------


def test_illegible_printed_line_cannot_be_compared() -> None:
    lines = list(all_printed())
    lines[2] = PrintedLine(
        C.ENERGY_CHARGE,
        "Energy",
        Traced.missing(reason="energy line illegible", status=VER, kind=Money),
    )
    report = run(bill(printed=tuple(lines), printed_total=entered(Money(TOTAL_A))))
    assert status_of(report, C.ENERGY_CHARGE) is LineStatus.CANNOT_COMPARE
    assert diff_of(report, C.ENERGY_CHARGE).missing_reasons() == ("energy line illegible",)
    # Both totals are known, so the total is still compared (D3).
    assert report.total.difference.value == Money(0)
    assert report.total.residual.is_missing
    assert report.explanation.state is ExplanationState.PARTIAL


def test_missing_calculated_lines_cannot_be_compared() -> None:
    report = run(bill(zones=None, printed=all_printed(), printed_total=entered(Money(TOTAL_A))))
    for code in (C.TOD_ADJUSTMENT, C.ELECTRICITY_DUTY, C.ROUNDING_OFF):
        assert status_of(report, code) is LineStatus.CANNOT_COMPARE
        assert diff_of(report, code).missing_reasons() == ("ToD zone readings not provided",)
    assert report.total.difference.is_missing
    assert report.total.difference.missing_reasons() == ("ToD zone readings not provided",)
    assert report.total.residual.value == Money(0)  # printed arithmetic is still checkable
    assert report.explanation.state is ExplanationState.PARTIAL


def test_absent_line_with_missing_calculation() -> None:
    lines = tuple(p for p in all_printed() if p.code is not C.TOD_ADJUSTMENT)
    report = run(bill(zones=None, printed=lines))
    assert status_of(report, C.TOD_ADJUSTMENT) is LineStatus.CANNOT_COMPARE
    note = diff_of(report, C.TOD_ADJUSTMENT).note
    assert "line not on printed bill and calculated amount missing" in note
    assert "ToD zone readings not provided" in note
    assert "no printed total was given" in report.total.difference.note
    assert "calculated total missing" in report.total.difference.note


# ---- NOT_RECALCULATED ----------------------------------------------------------------


def test_pass_through_lines_are_never_matches() -> None:
    rent, fee = other("Meter rent", "250"), other("Late fee", "12.34")
    report = run(
        bill(printed=(*all_printed(), rent, fee), printed_total=entered(Money(TOTAL_A + 26_234)))
    )
    passed = report.taken_as_printed
    assert [c.label for c in passed] == ["Meter rent", "Late fee"]
    for comparison in passed:
        assert comparison.status is LineStatus.NOT_RECALCULATED
        assert comparison.calculated is None
        assert comparison.difference.is_missing
        assert not comparison.is_compared
        assert comparison not in report.matches
    assert passed[0].printed is rent  # the user's own line, unchanged
    assert report.taken_as_printed_total.value == Money(26_234)
    assert len(report.recalculated) == 6
    assert report.explanation.state is ExplanationState.COMPLETE
    # Duty is 5,362,190 either way (pass-through lines are not in its base).
    # Subtotal 112,605,990 + 26,234 = 112,632,224 -> rupee half-up 112,632,200,
    # so SAMAY's rounding off is -24 while the printed one is +10.
    assert report.total.calculated.value == Money(112_632_200)
    assert report.total.difference.value == Money(34)  # 112,632,234 - 112,632,200
    assert report.total.residual.value == Money(0)  # printed lines add up to 112,632,234
    assert diff_of(report, C.ROUNDING_OFF).value == Money(34)  # +10 - (-24)


def test_nothing_taken_as_printed_is_missing_not_zero() -> None:
    report = run(bill(printed=all_printed()))
    assert report.taken_as_printed == ()
    assert report.taken_as_printed_total.is_missing


def test_missing_pass_through_amount_blocks_completeness() -> None:
    unknown = PrintedLine(
        C.OTHER, "Arrears", Traced.missing(reason="arrears illegible", status=VER, kind=Money)
    )
    report = run(bill(printed=(*all_printed(), unknown)))
    assert report.explanation.state is ExplanationState.PARTIAL
    assert report.taken_as_printed_total.is_missing
    assert report.total.calculated.is_missing


# ---- status, estimates and provenance -------------------------------------------------


def test_synthetic_tariff_reaches_every_difference() -> None:
    report = run(bill(printed=all_printed(), printed_total=entered(Money(TOTAL_A))))
    assert report.banner is not None
    for comparison in report.lines:
        assert comparison.difference.is_synthetic
    assert report.total.difference.is_synthetic


def test_estimated_printed_line_is_flagged_and_warned() -> None:
    lines = list(all_printed())
    lines[4] = PrintedLine(
        C.ELECTRICITY_DUTY,
        "Duty",
        Traced.estimated(Money(5_362_190), basis="duty digits smudged", status=VER),
    )
    report = run(
        bill(
            printed=tuple(lines),
            printed_total=Traced.estimated(Money(TOTAL_A), basis="total from photo", status=VER),
        )
    )
    duty = next(c for c in report.lines if c.code is C.ELECTRICITY_DUTY)
    assert duty.status is LineStatus.MATCH
    assert duty.rests_on_estimate
    assert duty.estimate_bases == ("duty digits smudged",)
    assert not next(c for c in report.lines if c.code is C.ENERGY_CHARGE).rests_on_estimate
    assert report.total.rests_on_estimate
    assert "total from photo" in report.total.estimate_bases
    assert report.rests_on_estimate
    messages = [i.message for i in report.issues if i.code == "input-estimated"]
    assert "printed line 'Duty' is an estimate: duty digits smudged" in messages
    assert "the printed total is an estimate: total from photo" in messages


def test_estimated_reading_flags_calculated_side() -> None:
    report = run(
        bill(
            kvah=Traced.estimated(
                ApparentEnergy("100000"), basis="kVAh from last month", status=VER
            ),
            printed=all_printed(),
        )
    )
    energy = next(c for c in report.lines if c.code is C.ENERGY_CHARGE)
    assert energy.rests_on_estimate
    assert energy.estimate_bases == ("kVAh from last month",)
    assert report.total.estimate_bases == ("kVAh from last month",)


def test_differences_keep_links_to_both_sides() -> None:
    report = run(bill(printed=all_printed(energy_charge=90_000_001)))
    energy = next(c for c in report.lines if c.code is C.ENERGY_CHARGE)
    assert energy.printed is not None
    assert energy.calculated is not None
    assert energy.difference.inputs == (energy.printed.amount, energy.calculated.amount)
    lines = tuple(p for p in all_printed() if p.code is not C.EXCESS_DEMAND_CHARGE)
    absent = next(c for c in run(bill(printed=lines)).lines if c.code is C.EXCESS_DEMAND_CHARGE)
    assert absent.calculated is not None
    assert absent.difference.inputs == (absent.calculated.amount,)


# ---- immutability and input checks ----------------------------------------------------


def test_reconcile_does_not_change_its_inputs() -> None:
    b = bill(
        printed=(*all_printed(energy_charge=1), other("Rent", "1")), printed_total=entered(Money(5))
    )
    breakdown = recompute_bill(b, SAMAY_DEMO_1)
    bill_before, breakdown_before = repr(b), repr(breakdown)
    bill_copy, breakdown_copy = copy.deepcopy(b), copy.deepcopy(breakdown)
    report = reconcile(b, breakdown)
    assert repr(b) == bill_before
    assert repr(breakdown) == breakdown_before
    assert b == bill_copy
    assert breakdown == breakdown_copy
    assert report.breakdown is breakdown
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.lines = ()  # type: ignore[misc]


def test_breakdown_must_come_from_this_bill() -> None:
    b = bill(printed=(other("Rent", "1"),))
    other_bill = dataclasses.replace(b, bill_id="SOMETHING-ELSE")
    with pytest.raises(ReconciliationInputError):
        reconcile(other_bill, recompute_bill(b, SAMAY_DEMO_1))
    copy_with_new_line = dataclasses.replace(b, printed_lines=(other("Rent", "1"),))
    with pytest.raises(ReconciliationInputError):
        reconcile(copy_with_new_line, recompute_bill(b, SAMAY_DEMO_1))
    with pytest.raises(TypeError):
        reconcile("bill", recompute_bill(b, SAMAY_DEMO_1))  # type: ignore[arg-type]


def test_duplicate_codes_are_refused_not_guessed() -> None:
    b = bill()
    duplicated = dataclasses.replace(
        b, printed_lines=(printed(C.ENERGY_CHARGE, 1), printed(C.ENERGY_CHARGE, 2))
    )
    with pytest.raises(ReconciliationInputError, match="two printed lines"):
        reconcile(duplicated, recompute_bill(b, SAMAY_DEMO_1))


# ---- property: the identity against an independent integer oracle --------------------


@given(
    st.dictionaries(st.sampled_from(list(EXAMPLE_A)), st.integers(-(10**6), 10**6), max_size=6),
    st.lists(st.integers(-(10**6), 10**6), max_size=3),
    st.integers(-(10**6), 10**6),
    st.sampled_from([SYN, VER]),
)
def test_line_and_total_results_against_oracle(
    changes: dict[ComponentCode, int], others: list[int], total_change: int, status: DataStatus
) -> None:
    printed_lines = [
        printed(code, paise + changes.get(code, 0), status) for code, paise in EXAMPLE_A.items()
    ]
    printed_lines += [
        PrintedLine(C.OTHER, f"other {i}", entered(Money(p), status)) for i, p in enumerate(others)
    ]
    printed_total = TOTAL_A + sum(changes.values()) + total_change
    report = run(
        bill(
            printed=tuple(printed_lines),
            printed_total=entered(Money(printed_total + sum(others))),
            status=status,
        )
    )
    # Oracle, from plain integers: calculated total with the 'other' lines added.
    subtotal = 112_605_990 + sum(others)
    calculated_total = (
        100 * ((subtotal + 50) // 100) if subtotal >= 0 else -100 * ((-subtotal + 50) // 100)
    )
    calculated_rounding = calculated_total - subtotal
    expected_lines = {**EXAMPLE_A, C.ROUNDING_OFF: calculated_rounding}
    for code, calculated in expected_lines.items():
        printed_amount = EXAMPLE_A[code] + changes.get(code, 0)
        expected = printed_amount - calculated
        assert diff_of(report, code).value == Money(expected)
        assert status_of(report, code) is (
            LineStatus.MATCH if expected == 0 else LineStatus.DIFFERS
        )
    assert report.total.difference.value == Money(printed_total + sum(others) - calculated_total)
    assert report.total.residual.value == Money(total_change)
    # The identity holds (checked by the engine too): total difference = lines + residual.
    line_sum = sum(diff_of(report, code).value.paise for code in expected_lines)
    assert report.total.difference.value.paise == line_sum + total_change
    assert report.explanation.state is ExplanationState.COMPLETE
    assert report.is_clean == (
        line_sum == 0 and total_change == 0 and report.total.difference.value == Money(0)
    )


@given(st.sets(st.sampled_from(list(EXAMPLE_A))))
def test_absent_lines_never_get_a_number(absent: set[ComponentCode]) -> None:
    lines = tuple(p for p in all_printed() if p.code not in absent)
    report = run(bill(printed=lines, printed_total=entered(Money(TOTAL_A))))
    for comparison in report.lines:
        if comparison.code in absent:
            assert comparison.status is LineStatus.CALCULATED_ONLY
            assert comparison.difference.is_missing
    expected = (
        ExplanationState.UNDETERMINABLE
        if len(absent) == 6
        else ExplanationState.PARTIAL
        if absent
        else ExplanationState.COMPLETE
    )
    assert report.explanation.state is expected
    assert report.total.difference.value == Money(0)


def test_zones_estimate_does_not_reach_untouched_lines() -> None:
    zones = ZoneConsumption(
        Traced.estimated(ApparentEnergy("25000"), basis="peak estimated", status=VER),
        entered(ApparentEnergy("30000")),
        entered(ApparentEnergy("45000")),
    )
    report = run(bill(tod=zones, printed=all_printed()))
    flagged = {c.code for c in report.lines if c.rests_on_estimate}
    assert flagged == {C.TOD_ADJUSTMENT, C.ELECTRICITY_DUTY, C.ROUNDING_OFF}
