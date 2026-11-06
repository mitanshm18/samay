"""Compare a printed bill with SAMAY's recalculation (Step 3B, decision 0004).

Every difference is printed minus calculated, in integer paise, with zero
tolerance. Nothing is ever adjusted, rounded or assumed:

- A calculated line with no printed line is CALCULATED_ONLY. Its difference
  is undetermined (absence is not a printed ₹0) and it is never a match.
- A missing amount on either side makes the line CANNOT_COMPARE.
- Printed 'other' lines are NOT_RECALCULATED: never compared, never matches,
  only reported as "taken as printed".

The total comparison (printed total minus calculated total) is independent
of the lines, and the line-by-line explanation is reported separately as
COMPLETE, PARTIAL or UNDETERMINABLE. Neither result implies the other.

reconcile() only reads its frozen inputs and builds new objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from samay.core import DataStatus, Money, Provenance, SamayCoreError, Traced, combine_status
from samay.tariffs import ComponentCode

from .breakdown import BillBreakdown, LineBasis, MoneyLine
from .inputs import BillInput, PrintedLine
from .validation import ValidationIssue


class ReconciliationInputError(SamayCoreError, ValueError):
    """The breakdown was not calculated from this bill."""


class ReconciliationInvariantError(SamayCoreError, AssertionError):
    """An internal consistency check failed. This is a bug in SAMAY, not in the input."""


class LineStatus(Enum):
    MATCH = "match"
    DIFFERS = "differs"
    CALCULATED_ONLY = "calculated only"  # not on the printed bill; difference undetermined
    CANNOT_COMPARE = "cannot compare"  # an amount is missing on one or both sides
    NOT_RECALCULATED = "not recalculated"  # printed 'other' line, taken as printed


class ExplanationState(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNDETERMINABLE = "undeterminable"


def _difference(printed: Money, calculated: Money) -> Money:
    return printed - calculated


def _sum(*amounts: Money) -> Money:
    return sum(amounts, Money.zero())


def _undetermined(reason: str, *inputs: Traced[Any]) -> Traced[Money]:
    """A MISSING difference that keeps links to the values it concerns."""
    return Traced(
        None, Provenance.MISSING, combine_status(i.status for i in inputs), reason, inputs
    )


def _estimate_bases(*values: Traced[Any]) -> tuple[str, ...]:
    bases: list[str] = []
    for value in values:
        for leaf in value.leaves():
            if leaf.provenance is Provenance.ESTIMATED and leaf.note not in bases:
                bases.append(leaf.note)
    return tuple(bases)


@dataclass(frozen=True, slots=True)
class LineComparison:
    """One line of the reconciliation. difference is MISSING unless MATCH or DIFFERS."""

    code: ComponentCode
    label: str
    status: LineStatus
    printed: PrintedLine | None  # the user's printed line, unchanged; None if not printed
    calculated: MoneyLine | None  # SAMAY's line, unchanged; None for NOT_RECALCULATED
    difference: Traced[Money]  # printed - calculated, in paise

    @property
    def is_compared(self) -> bool:
        return self.status in (LineStatus.MATCH, LineStatus.DIFFERS)

    def _sides(self) -> tuple[Traced[Money], ...]:
        sides = []
        if self.printed is not None:
            sides.append(self.printed.amount)
        if self.calculated is not None:
            sides.append(self.calculated.amount)
        return tuple(sides)

    @property
    def rests_on_estimate(self) -> bool:
        return any(side.rests_on_estimate for side in self._sides())

    @property
    def estimate_bases(self) -> tuple[str, ...]:
        return _estimate_bases(*self._sides())


@dataclass(frozen=True, slots=True)
class TotalComparison:
    """Printed total minus calculated total, independent of the line comparisons."""

    printed: Traced[Money] | None  # None when the bill input gives no printed total
    calculated: Traced[Money]
    difference: Traced[Money]  # MISSING (with reasons) unless both totals are known
    residual: Traced[Money]  # printed total minus the sum of printed lines (printed arithmetic)

    @property
    def rests_on_estimate(self) -> bool:
        return self.difference.rests_on_estimate or self.residual.rests_on_estimate

    @property
    def estimate_bases(self) -> tuple[str, ...]:
        sides = [self.calculated] if self.printed is None else [self.printed, self.calculated]
        return _estimate_bases(*sides)


@dataclass(frozen=True, slots=True)
class LineExplanation:
    """How far the lines explain the bill. No unattributed remainder is ever shown."""

    state: ExplanationState
    compared: tuple[LineComparison, ...]  # MATCH and DIFFERS
    not_compared: tuple[LineComparison, ...]  # CALCULATED_ONLY and CANNOT_COMPARE
    compared_difference: Traced[Money]  # sum of differences on compared lines

    @property
    def reasons(self) -> tuple[str, ...]:
        """Why each line that could not be compared was not compared."""
        return tuple(f"{c.label}: {c.difference.note}" for c in self.not_compared)


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    bill_id: str
    tariff_id: str
    tariff_name: str
    tariff_status: DataStatus
    banner: str | None
    breakdown: BillBreakdown
    lines: tuple[LineComparison, ...]  # recalculated lines in bill order, then 'other' lines
    total: TotalComparison
    explanation: LineExplanation
    issues: tuple[ValidationIssue, ...]

    def _with(self, *statuses: LineStatus) -> tuple[LineComparison, ...]:
        return tuple(line for line in self.lines if line.status in statuses)

    @property
    def matches(self) -> tuple[LineComparison, ...]:
        return self._with(LineStatus.MATCH)

    @property
    def differences(self) -> tuple[LineComparison, ...]:
        return self._with(LineStatus.DIFFERS)

    @property
    def recalculated(self) -> tuple[LineComparison, ...]:
        """Every line SAMAY recalculated (all statuses except NOT_RECALCULATED)."""
        return tuple(line for line in self.lines if line.status is not LineStatus.NOT_RECALCULATED)

    @property
    def taken_as_printed(self) -> tuple[LineComparison, ...]:
        return self._with(LineStatus.NOT_RECALCULATED)

    @property
    def taken_as_printed_total(self) -> Traced[Money]:
        """From breakdown.not_recalculated_lines; MISSING when nothing was taken as printed."""
        return self.breakdown.not_recalculated_total

    @property
    def is_clean(self) -> bool:
        """Everything recalculated was compared and matches, and the totals agree exactly."""
        difference = self.total.difference
        return (
            self.explanation.state is ExplanationState.COMPLETE
            and all(line.status is LineStatus.MATCH for line in self.recalculated)
            and not difference.is_missing
            and difference.value == Money.zero()
        )

    @property
    def rests_on_estimate(self) -> bool:
        return any(line.rests_on_estimate for line in self.lines) or self.total.rests_on_estimate


def _compare(code: ComponentCode, printed: PrintedLine | None, line: MoneyLine) -> LineComparison:
    calculated = line.amount
    if printed is None:
        # D1: a line absent from the printed bill is CALCULATED_ONLY whether or
        # not SAMAY could calculate it; the reason records which.
        status = LineStatus.CALCULATED_ONLY
        if calculated.is_missing:
            difference = _undetermined(
                "line not on printed bill and calculated amount missing "
                f"({'; '.join(calculated.missing_reasons())})",
                calculated,
            )
        else:
            difference = _undetermined("line not on printed bill", calculated)
    else:
        difference = Traced.derive(
            _difference,
            printed.amount,
            calculated,
            description=f"{line.label}: printed - calculated",
        )
        if difference.is_missing:
            status = LineStatus.CANNOT_COMPARE
        elif difference.value == Money.zero():
            status = LineStatus.MATCH
        else:
            status = LineStatus.DIFFERS
    return LineComparison(code, line.label, status, printed, line, difference)


def reconcile(bill: BillInput, breakdown: BillBreakdown) -> ReconciliationReport:
    """Compare the printed lines and total of bill with its recalculation."""
    if not isinstance(bill, BillInput) or not isinstance(breakdown, BillBreakdown):
        raise TypeError("reconcile() needs a BillInput and its BillBreakdown")
    passed = bill.pass_through_lines
    if (
        breakdown.bill_id != bill.bill_id
        or len(passed) != len(breakdown.not_recalculated_lines)
        or any(
            p.amount is not m.amount
            for p, m in zip(passed, breakdown.not_recalculated_lines, strict=True)
        )
    ):
        raise ReconciliationInputError(
            f"the breakdown for {breakdown.bill_id!r} was not calculated from bill {bill.bill_id!r}"
        )

    printed_by_code: dict[ComponentCode, PrintedLine] = {}
    for printed in bill.printed_lines:
        if printed.code is not ComponentCode.OTHER:
            if printed.code in printed_by_code:  # validation forbids this; never pick one
                raise ReconciliationInputError(f"two printed lines are tagged {printed.code.value}")
            printed_by_code[printed.code] = printed

    comparisons: list[LineComparison] = []
    for line in breakdown.lines:
        if line.basis is LineBasis.RECALCULATED:
            comparisons.append(_compare(line.code, printed_by_code.get(line.code), line))
    for printed in passed:  # same order as breakdown.not_recalculated_lines (checked above)
        comparisons.append(
            LineComparison(
                printed.code,
                printed.label,
                LineStatus.NOT_RECALCULATED,
                printed,
                None,
                _undetermined("not recalculated: taken as printed, not checked", printed.amount),
            )
        )
    lines = tuple(comparisons)

    total = _total(bill, breakdown)
    explanation = _explain(lines, total, breakdown)
    return ReconciliationReport(
        bill_id=bill.bill_id,
        tariff_id=breakdown.tariff_id,
        tariff_name=breakdown.tariff_name,
        tariff_status=breakdown.tariff_status,
        banner=breakdown.banner,
        breakdown=breakdown,
        lines=lines,
        total=total,
        explanation=explanation,
        issues=breakdown.issues,
    )


def _total(bill: BillInput, breakdown: BillBreakdown) -> TotalComparison:
    calculated = breakdown.total
    printed = bill.printed_total
    if printed is None:
        difference = _undetermined(
            "no printed total was given"
            + (
                f"; calculated total missing ({'; '.join(calculated.missing_reasons())})"
                if calculated.is_missing
                else ""
            ),
            calculated,
        )
        residual = _undetermined("no printed total was given", calculated)
    else:
        difference = Traced.derive(
            _difference, printed, calculated, description="total: printed - calculated"
        )
        amounts = [line.amount for line in bill.printed_lines]
        if not amounts:
            residual = _undetermined("no printed lines were given", printed)
        else:

            def residual_of(total: Money, *lines: Money) -> Money:
                return total - _sum(*lines)

            residual = Traced.derive(
                residual_of,
                printed,
                *amounts,
                description="printed total - sum of printed lines",
            )
    return TotalComparison(printed, calculated, difference, residual)


def _explain(
    lines: tuple[LineComparison, ...], total: TotalComparison, breakdown: BillBreakdown
) -> LineExplanation:
    compared = tuple(line for line in lines if line.is_compared)
    not_compared = tuple(
        line
        for line in lines
        if line.status in (LineStatus.CALCULATED_ONLY, LineStatus.CANNOT_COMPARE)
    )
    passed_known = all(
        not line.printed.amount.is_missing
        for line in lines
        if line.status is LineStatus.NOT_RECALCULATED and line.printed is not None
    )
    if not compared:
        state = ExplanationState.UNDETERMINABLE
        compared_difference = Traced.missing(
            reason="no line could be compared", status=breakdown.tariff_status, kind=Money
        )
    else:
        state = (
            ExplanationState.COMPLETE
            if not not_compared and passed_known
            else ExplanationState.PARTIAL
        )
        compared_difference = Traced.derive(
            _sum,
            *(line.difference for line in compared),
            description="sum of differences on compared lines",
        )
    if state is ExplanationState.COMPLETE:
        _check_identity(total, compared_difference)
    return LineExplanation(state, compared, not_compared, compared_difference)


def _check_identity(total: TotalComparison, compared_difference: Traced[Money]) -> None:
    """When every line is known: printed - calculated total = line differences + residual."""
    if total.difference.is_missing or total.residual.is_missing:
        return
    expected = compared_difference.value + total.residual.value
    if total.difference.value != expected:  # pragma: no cover - would be a SAMAY bug
        raise ReconciliationInvariantError(
            f"total difference {total.difference.value} != line differences "
            f"{compared_difference.value} + residual {total.residual.value}"
        )
