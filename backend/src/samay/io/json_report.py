"""SAMAY's JSON output (samay.report/1, docs/json-format.md).

- Every amount and measurement carries its provenance, data status, note,
  estimate flags and the original values (leaves) it rests on (D6).
  Counts and status labels are plain metadata without provenance.
- Every number is a string; null appears only for a MISSING value.
- Key order is fixed, so the same input always gives the same bytes.
- Synthetic status, warnings and errors are inside the JSON (D9).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from samay.billing import (
    BillBreakdown,
    LineComparison,
    LineStatus,
    MoneyLine,
    QuantityLine,
    ReconciliationReport,
    ValidationIssue,
)
from samay.core import (
    DataStatus,
    ExactAmount,
    ExactApparentPower,
    Money,
    PowerFactor,
    Provenance,
    Quantity,
    QuantityRounding,
    Rate,
    Traced,
)
from samay.core._decimal import EXACT

from .errors import InputError

FORMAT = "samay.report/1"


def _decimal_text(value: Decimal) -> str:
    return f"{value:f}"


def render_value(raw: object) -> dict[str, str]:
    """A SAMAY value as strings. Unknown types are a programming error."""
    if isinstance(raw, Money):
        return {"value": _decimal_text(raw.to_rupees()), "unit": "INR", "paise": str(raw.paise)}
    if isinstance(raw, ExactAmount):
        rupees = EXACT.scaleb(raw.paise, -2)
        return {"value": _decimal_text(rupees), "unit": "INR (exact, unrounded)"}
    if isinstance(raw, Quantity | ExactApparentPower):
        return {"value": _decimal_text(raw.value), "unit": raw.UNIT.value}
    if isinstance(raw, PowerFactor):
        ratio = raw.ratio
        return {
            "value": f"{ratio.numerator}/{ratio.denominator}",
            "unit": "ratio (exact)",
            "rounded_3_places_half_up": _decimal_text(
                raw.rounded(3, rounding=QuantityRounding.HALF_UP)
            ),
        }
    if isinstance(raw, Rate):
        return {
            "value": _decimal_text(raw.paise_per_unit),
            "unit": f"paise/{raw.unit.value}",
            "basis": raw.basis.value,
        }
    if isinstance(raw, Decimal):
        return {"value": _decimal_text(raw)}
    raise TypeError(f"no JSON rendering for {type(raw).__name__}")


def _leaf(leaf: Traced[Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "provenance": leaf.provenance.value,
        "status": leaf.status.value,
        "note": leaf.note,
    }
    if leaf.is_missing:
        data["value"] = None
    else:
        data.update(render_value(leaf.raw))
    return data


def traced(value: Traced[Any]) -> dict[str, Any]:
    """A traced amount or measurement with everything it rests on."""
    data: dict[str, Any] = {}
    if value.is_missing:
        data["value"] = None
    else:
        data.update(render_value(value.raw))
    data["provenance"] = value.provenance.value
    data["status"] = value.status.value
    data["note"] = value.note
    if value.is_missing:
        data["missing_reasons"] = list(value.missing_reasons())
    data["rests_on_estimate"] = value.rests_on_estimate
    data["estimate_bases"] = [
        leaf.note for leaf in value.leaves() if leaf.provenance is Provenance.ESTIMATED
    ]
    if value.inputs:
        data["leaves"] = [_leaf(leaf) for leaf in value.leaves()]
    return data


def issue(item: ValidationIssue) -> dict[str, str]:
    return {"severity": item.severity.value, "code": item.code, "message": item.message}


def input_error(item: InputError) -> dict[str, str]:
    return {"path": item.path, "code": item.code, "message": item.message}


def _quantity(line: QuantityLine) -> dict[str, Any]:
    return {"key": line.key, "label": line.label, "formula": line.formula, **traced(line.value)}


def _money_line(line: MoneyLine) -> dict[str, Any]:
    return {
        "code": line.code.value,
        "label": line.label,
        "basis": line.basis.value,
        "formula": line.formula,
        "rounding": None if line.rounding is None else line.rounding.value,
        "exact": None if line.exact is None else traced(line.exact),
        "amount": traced(line.amount),
        "assumptions": [{"key": a.key, "text": a.text} for a in line.assumptions],
    }


def _header(command: str, exit_code: int) -> dict[str, Any]:
    return {"format": FORMAT, "command": command, "exit_code": str(exit_code)}


def _tariff(tariff_id: str, name: str, status: DataStatus, banner: str | None) -> dict[str, Any]:
    return {
        "tariff": {"id": tariff_id, "name": name, "status": status.value},
        "synthetic": status is DataStatus.SYNTHETIC,
        "banner": banner,
    }


def breakdown(result: BillBreakdown) -> dict[str, Any]:
    return {
        "bill_id": result.bill_id,
        "complete": result.is_complete,
        "quantities": [_quantity(q) for q in result.quantities],
        "lines": [_money_line(line) for line in result.lines],
        "subtotal": traced(result.subtotal),
        "total": traced(result.total),
        "taken_as_printed": {
            "line_count": str(len(result.not_recalculated_lines)),
            "total": traced(result.not_recalculated_total),
        },
        "rests_on_estimate": result.rests_on_estimate,
        "estimate_bases": list(result.estimate_bases),
        "assumptions": [{"key": a.key, "text": a.text} for a in result.assumptions],
    }


def _comparison(line: LineComparison) -> dict[str, Any]:
    data: dict[str, Any] = {
        "code": line.code.value,
        "label": line.label,
        "status": line.status.name,
        "on_printed_bill": line.printed is not None,
    }
    if line.printed is not None:
        data["printed"] = traced(line.printed.amount)
    if line.calculated is not None:
        data["calculated"] = traced(line.calculated.amount)
    data["difference"] = traced(line.difference)
    data["rests_on_estimate"] = line.rests_on_estimate
    data["estimate_bases"] = list(line.estimate_bases)
    return data


def _count(report: ReconciliationReport, status: LineStatus) -> str:
    return str(sum(1 for line in report.lines if line.status is status))


def reconciliation(report: ReconciliationReport) -> dict[str, Any]:
    total = report.total
    total_data: dict[str, Any] = {"printed_total_given": total.printed is not None}
    if total.printed is not None:
        total_data["printed"] = traced(total.printed)
    total_data["calculated"] = traced(total.calculated)
    total_data["difference"] = traced(total.difference)
    total_data["printed_lines_residual"] = traced(total.residual)
    explanation = report.explanation
    return {
        "lines": [_comparison(line) for line in report.lines],
        "total": total_data,
        "explanation": {
            "state": explanation.state.name,
            "compared_line_count": str(len(explanation.compared)),
            "compared_difference": traced(explanation.compared_difference),
            "not_compared": [
                {
                    "code": c.code.value,
                    "label": c.label,
                    "status": c.status.name,
                    "reason": c.difference.note,
                }
                for c in explanation.not_compared
            ],
        },
        "counts": {
            "recalculated_lines": str(len(report.recalculated)),
            "match": str(len(report.matches)),
            "differs": str(len(report.differences)),
            "calculated_only": _count(report, LineStatus.CALCULATED_ONLY),
            "cannot_compare": _count(report, LineStatus.CANNOT_COMPARE),
            "not_recalculated": str(len(report.taken_as_printed)),
        },
        "taken_as_printed_total": traced(report.taken_as_printed_total),
        "clean": report.is_clean,
        "rests_on_estimate": report.rests_on_estimate,
    }


def calculation_document(result: BillBreakdown, exit_code: int) -> dict[str, Any]:
    return {
        **_header("calculate", exit_code),
        **_tariff(result.tariff_id, result.tariff_name, result.tariff_status, result.banner),
        "warnings": [issue(i) for i in result.issues],
        "errors": [],
        "calculation": breakdown(result),
    }


def reconciliation_document(report: ReconciliationReport, exit_code: int) -> dict[str, Any]:
    return {
        **_header("reconcile", exit_code),
        **_tariff(report.tariff_id, report.tariff_name, report.tariff_status, report.banner),
        "warnings": [issue(i) for i in report.issues],
        "errors": [],
        "calculation": breakdown(report.breakdown),
        "reconciliation": reconciliation(report),
    }


def validation_document(
    command: str,
    exit_code: int,
    *,
    errors: tuple[InputError, ...] = (),
    warnings: tuple[ValidationIssue, ...] = (),
    tariff: tuple[str, str, DataStatus, str | None] | None = None,
) -> dict[str, Any]:
    data = _header(command, exit_code)
    data["valid"] = not errors
    if tariff is not None:
        data.update(_tariff(*tariff))
    data["warnings"] = [issue(w) for w in warnings]
    data["errors"] = [input_error(e) for e in errors]
    return data


def internal_error_document(command: str, message: str) -> dict[str, Any]:
    return {**_header(command, 3), "internal_error": message}


def dumps(document: dict[str, Any]) -> str:
    """Deterministic JSON text. Every value is a string, bool, list, object or null."""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
