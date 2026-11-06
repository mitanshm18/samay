"""The result of a bill calculation: every line, how it was reached, and on what it rests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from samay.core import DataStatus, ExactAmount, Money, Provenance, RoundingRule, Traced
from samay.tariffs import Assumption, ComponentCode

from .validation import ValidationIssue


class LineBasis(Enum):
    RECALCULATED = "recalculated"  # SAMAY computed it from readings and the tariff
    NOT_RECALCULATED = "not recalculated"  # taken as printed (an 'other' line)


@dataclass(frozen=True, slots=True)
class QuantityLine:
    """A quantity used in the bill (a reading, or one derived from readings)."""

    key: str
    label: str
    value: Traced[Any]
    formula: str


@dataclass(frozen=True, slots=True)
class MoneyLine:
    """One money line of the bill.

    For a RECALCULATED line, exact is the unrounded amount and rounding the
    one rule applied to it. A NOT_RECALCULATED line has neither: it keeps the
    printed amount and its own provenance.
    """

    code: ComponentCode
    label: str
    basis: LineBasis
    amount: Traced[Money]
    exact: Traced[ExactAmount] | None
    rounding: RoundingRule | None
    formula: str
    assumptions: tuple[Assumption, ...]

    @property
    def is_missing(self) -> bool:
        return self.amount.is_missing

    @property
    def rests_on_estimate(self) -> bool:
        """True if this amount was derived from (or is) an ESTIMATED value."""
        return self.amount.rests_on_estimate

    @property
    def estimate_bases(self) -> tuple[str, ...]:
        """The stated basis of each estimate behind this amount (empty if none)."""
        return tuple(
            leaf.note for leaf in self.amount.leaves() if leaf.provenance is Provenance.ESTIMATED
        )


@dataclass(frozen=True, slots=True)
class BillBreakdown:
    """A recalculated bill. Every money line appears once, and total = sum of lines."""

    bill_id: str
    tariff_id: str
    tariff_name: str
    tariff_status: DataStatus
    banner: str | None  # shown above everything when the tariff is synthetic
    quantities: tuple[QuantityLine, ...]
    charges: tuple[MoneyLine, ...]  # C2..C7, the lines that make up the subtotal
    subtotal: Traced[Money]  # C8, not itself a line
    rounding_off: MoneyLine  # C9
    total: Traced[Money]  # C8 + C9 = sum of all money lines
    assumptions: tuple[Assumption, ...]
    issues: tuple[ValidationIssue, ...]  # warnings only; errors stop the calculation

    @property
    def lines(self) -> tuple[MoneyLine, ...]:
        """All money lines in bill order: the charges, then rounding off."""
        return (*self.charges, self.rounding_off)

    def line(self, code: ComponentCode) -> MoneyLine:
        """The one line with this code (not for 'other', which can repeat)."""
        found = [line for line in self.lines if line.code is code]
        if len(found) != 1:
            raise KeyError(f"{len(found)} lines with code {code.value}")
        return found[0]

    def quantity(self, key: str) -> QuantityLine:
        for item in self.quantities:
            if item.key == key:
                return item
        raise KeyError(key)

    @property
    def is_complete(self) -> bool:
        return not self.total.is_missing

    @property
    def not_recalculated_lines(self) -> tuple[MoneyLine, ...]:
        """The lines taken as printed, not recalculated (printed 'other' lines)."""
        return tuple(line for line in self.charges if line.basis is LineBasis.NOT_RECALCULATED)

    @property
    def not_recalculated_total(self) -> Traced[Money]:
        """The sum of lines taken as printed: 'Rs X taken as printed and not checked'.

        With no such lines there is no printed amount to add up, so the result
        is MISSING with that reason. It is never a made-up ENTERED zero (M3);
        a report shows "nothing taken as printed" instead of an amount.
        """
        passed = [line.amount for line in self.not_recalculated_lines]
        if not passed:
            return Traced.missing(
                reason="no printed 'other' lines: nothing was taken as printed",
                status=self.tariff_status,
                kind=Money,
            )
        return Traced.derive(_sum, *passed, description="lines taken as printed")

    @property
    def rests_on_estimate(self) -> bool:
        """True if the total, or any line, depends on an ESTIMATED input."""
        return self.total.rests_on_estimate or any(line.rests_on_estimate for line in self.lines)

    @property
    def estimate_bases(self) -> tuple[str, ...]:
        """The stated basis of every estimate the bill rests on, in first-seen order."""
        bases: list[str] = []
        for line in self.lines:
            for basis in line.estimate_bases:
                if basis not in bases:
                    bases.append(basis)
        return tuple(bases)


def _sum(*amounts: Money) -> Money:
    return sum(amounts, Money.zero())
