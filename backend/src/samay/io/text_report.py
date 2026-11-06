"""Human-readable reports. Built from the same objects as the JSON report.

The synthetic banner is always the first line. Missing values are written
as MISSING with their reasons, never as 0. Pass-through lines are listed as
taken as printed, never as matches.
"""

from __future__ import annotations

from samay.billing import (
    BillBreakdown,
    LineBasis,
    LineComparison,
    LineStatus,
    ReconciliationReport,
    ValidationIssue,
)
from samay.core import Money, Traced

from .errors import InputError


def _money(value: Traced[Money]) -> str:
    if value.is_missing:
        return "MISSING (" + "; ".join(value.missing_reasons()) + ")"
    text = value.value.format_inr()
    if value.rests_on_estimate:
        text += " [rests on an estimate]"
    return text


def _undetermined(value: Traced[Money]) -> str:
    return "not determinable (" + "; ".join(value.missing_reasons()) + ")"


def _signed(value: Traced[Money]) -> str:
    if value.is_missing:
        return _undetermined(value)
    amount = value.value
    sign = "+" if amount.paise > 0 else ""
    return f"{sign}{amount.format_inr()} ({sign}{amount.paise} paise)"


def _banner(lines: list[str], banner: str | None) -> None:
    if banner is not None:
        lines.append(f"*** {banner} ***")
        lines.append("")


def _issues(lines: list[str], issues: tuple[ValidationIssue, ...]) -> None:
    if issues:
        lines.append("Warnings:")
        lines.extend(f"  - {issue.message} [{issue.code}]" for issue in issues)
        lines.append("")


def errors_text(errors: tuple[InputError, ...]) -> str:
    lines = [f"The bill file has {len(errors)} problem(s):"]
    lines.extend(f"  - {e.path}: {e.message} [{e.code}]" for e in errors)
    return "\n".join(lines) + "\n"


def validation_text(bill_id: str, banner: str | None, issues: tuple[ValidationIssue, ...]) -> str:
    lines: list[str] = []
    _banner(lines, banner)
    lines.append(f"Bill {bill_id}: valid.")
    lines.append("")
    _issues(lines, issues)
    return "\n".join(lines).rstrip("\n") + "\n"


def _breakdown_lines(result: BillBreakdown, lines: list[str]) -> None:
    lines.append(f"Bill {result.bill_id}, tariff {result.tariff_id} ({result.tariff_status.value})")
    lines.append("")
    lines.append("Quantities:")
    for item in result.quantities:
        if item.formula == "read":
            shown = "MISSING" if item.value.is_missing else str(item.value.value)
            lines.append(f"  {item.label}: {shown}")
        else:
            lines.append(f"  {item.label}: {item.formula}")
    lines.append("")
    lines.append("Lines:")
    for line in result.lines:
        passed = line.basis is LineBasis.NOT_RECALCULATED
        tag = " (taken as printed, not recalculated)" if passed else ""
        lines.append(f"  {line.label}: {_money(line.amount)}{tag}")
        if not tag:
            lines.append(f"      {line.formula}")
    lines.append(f"  Subtotal: {_money(result.subtotal)}")
    lines.append(f"  Payable total: {_money(result.total)}")
    if result.estimate_bases:
        lines.append("")
        lines.append("Rests on estimates: " + "; ".join(result.estimate_bases))
    lines.append("")
    lines.append("Assumptions:")
    lines.extend(f"  - {a.text}" for a in result.assumptions)
    lines.append("")


def calculation_text(result: BillBreakdown) -> str:
    lines: list[str] = []
    _banner(lines, result.banner)
    _breakdown_lines(result, lines)
    _issues(lines, result.issues)
    return "\n".join(lines).rstrip("\n") + "\n"


def _comparison_line(line: LineComparison) -> str:
    printed = "not on printed bill" if line.printed is None else _money(line.printed.amount)
    if line.status is LineStatus.NOT_RECALCULATED:
        return f"  {line.label}: {printed} - taken as printed, not checked"
    calculated = _money(line.calculated.amount) if line.calculated is not None else "-"
    text = f"  {line.label}: {line.status.name}; printed {printed}, SAMAY {calculated}"
    if line.is_compared:
        text += f"; difference {_signed(line.difference)}"
    else:
        text += f"; difference {_undetermined(line.difference)}"
    return text


def reconciliation_text(report: ReconciliationReport) -> str:
    lines: list[str] = []
    _banner(lines, report.banner)
    _breakdown_lines(report.breakdown, lines)
    lines.append("Reconciliation (printed minus SAMAY, zero tolerance):")
    lines.extend(_comparison_line(line) for line in report.lines)
    lines.append("")
    total = report.total
    lines.append("Total (compared independently of the lines):")
    printed_total = "not given" if total.printed is None else _money(total.printed)
    lines.append(f"  Printed total: {printed_total}")
    lines.append(f"  SAMAY total: {_money(total.calculated)}")
    lines.append(f"  Difference: {_signed(total.difference)}")
    lines.append(f"  Printed lines vs printed total (residual): {_signed(total.residual)}")
    lines.append("")
    explanation = report.explanation
    recalculated = len(report.recalculated)
    lines.append(
        f"Lines: {explanation.state.name}; {len(report.matches)} of {recalculated} "
        f"recalculated lines match, {len(report.differences)} differ, "
        f"{len(explanation.not_compared)} not compared."
    )
    for line in explanation.not_compared:
        lines.append(f"  - {line.label}: {_undetermined(line.difference)}")
    passed = report.taken_as_printed_total
    if passed.is_missing and not report.taken_as_printed:
        lines.append("Nothing was taken as printed.")
    else:
        lines.append(f"{_money(passed)} taken as printed and not checked.")
    lines.append(
        "A matching total does not mean the lines match, and matching lines do not mean "
        "the total matches; both are reported separately above."
    )
    lines.append("")
    _issues(lines, report.issues)
    return "\n".join(lines).rstrip("\n") + "\n"
