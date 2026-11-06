"""Checks on a bill input before anything is calculated.

ERROR issues stop the calculation (recompute_bill raises BillValidationError).
WARNING issues are reported with the breakdown but do not change any number.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from samay.core import ApparentEnergy, Provenance, SamayCoreError
from samay.tariffs import ComponentCode, Tariff

from .inputs import BillInput

MIN_PERIOD = timedelta(days=28)
MAX_PERIOD = timedelta(days=31)


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.value}: {self.message} [{self.code}]"


class BillValidationError(SamayCoreError, ValueError):
    """The bill input has ERROR issues; nothing was calculated."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(str(issue) for issue in issues))


def validate_bill(bill: BillInput, tariff: Tariff) -> tuple[ValidationIssue, ...]:
    """Every issue found, errors first, in a stable order."""
    if not isinstance(bill, BillInput):
        raise TypeError("validate_bill() needs a BillInput")
    if not isinstance(tariff, Tariff):
        raise TypeError("validate_bill() needs a Tariff")
    issues: list[ValidationIssue] = []

    def error(code: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.ERROR, code, message))

    def warning(code: str, message: str) -> None:
        issues.append(ValidationIssue(Severity.WARNING, code, message))

    cd = bill.contract_demand
    if not cd.is_missing and cd.value.value == 0:
        error("contract-demand-zero", "contract demand must be greater than 0 kVA")

    kwh, kvah = bill.kwh, bill.kvah
    if not kwh.is_missing and not kvah.is_missing and kwh.value.value > kvah.value.value:
        error(
            "kwh-above-kvah",
            f"kWh ({kwh.value}) is greater than kVAh ({kvah.value}); "
            "active energy cannot exceed apparent energy",
        )

    if bill.zones is None:
        warning(
            "tod-zones-missing",
            "no time-of-day zone readings: the ToD adjustment and the total cannot be calculated",
        )
    else:
        known = [value.value for _, value in bill.zones.items() if not value.is_missing]
        known_sum = sum(known, ApparentEnergy.zero())
        if kvah.is_missing:
            warning(
                "tod-zones-unchecked",
                "kVAh is missing, so the zone readings cannot be checked against it",
            )
        elif bill.zones.is_complete:
            if known_sum != kvah.value:
                error(
                    "tod-zones-sum",
                    f"the ToD zones add up to {known_sum}, but total kVAh is {kvah.value}",
                )
        elif known_sum > kvah.value:
            error(
                "tod-zones-exceed",
                f"the known ToD zones already add up to {known_sum}, more than total "
                f"kVAh {kvah.value}",
            )
        if not bill.zones.is_complete:
            missing = [z.value for z, v in bill.zones.items() if v.is_missing]
            warning(
                "tod-zones-partial",
                f"ToD zone readings missing for {', '.join(missing)}: the ToD adjustment "
                "and the total cannot be calculated",
            )

    counts = Counter(line.code for line in bill.printed_lines)
    for code, count in counts.items():
        if code is not ComponentCode.OTHER and count > 1:
            error(
                "duplicate-printed-code",
                f"{count} printed lines are tagged {code.value}; only 'other' may repeat",
            )

    length = bill.period.end - bill.period.start
    if length < MIN_PERIOD or length > MAX_PERIOD:
        warning(
            "unusual-period",
            f"the billing period is {length}, outside 28 to 31 days; charges are not "
            "prorated, so check the period",
        )

    for name, value in (
        ("contract demand", cd),
        ("recorded maximum demand", bill.recorded_md),
        ("kWh", kwh),
        ("kVAh", kvah),
    ):
        if value.is_missing:
            warning("input-missing", f"{name} is missing: {value.note}")
        elif value.provenance is Provenance.ESTIMATED:
            warning("input-estimated", f"{name} is an estimate: {value.note}")
    for printed in bill.printed_lines:
        if printed.amount.provenance is Provenance.ESTIMATED:
            warning(
                "input-estimated",
                f"printed line {printed.label!r} is an estimate: {printed.amount.note}",
            )
    if bill.printed_total is not None and bill.printed_total.provenance is Provenance.ESTIMATED:
        warning("input-estimated", f"the printed total is an estimate: {bill.printed_total.note}")
    if bill.zones is not None:
        for zone, value in bill.zones.items():
            if value.provenance is Provenance.ESTIMATED:
                warning("input-estimated", f"{zone.value} zone kVAh is an estimate: {value.note}")

    if tariff.is_synthetic:
        warning(
            "synthetic-tariff",
            f"{tariff.tariff_id} is a synthetic tariff: the result is not a real bill",
        )

    return tuple(sorted(issues, key=lambda issue: issue.severity is not Severity.ERROR))
