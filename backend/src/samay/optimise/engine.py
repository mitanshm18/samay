"""Cost optimisation: explainable opportunities to reduce future electricity cost.

Pure and deterministic, like the rest of the engine: no database, API or UI.

Every rupee figure here is produced by SAMAY's own bill engine. A scenario is the
same bill with one stated change (for example "maximum demand at contract demand"),
recalculated by recompute_bill() with the same tariff; the saving is the current
total minus the scenario total, in integer paise. This module never multiplies a
rate by a quantity itself, so it cannot disagree with the bill calculation.

Honesty rules (decision 0008):
- Only values on the bill are used. Nothing is invented; a value that is MISSING
  gives "Insufficient data" with the reason, never an estimate.
- A saving computed with a SYNTHETIC tariff is ILLUSTRATIVE: it shows how the
  mechanism works and is never a real-world saving. Only a verified tariff gives
  an ESTIMATED saving.
- ACTIONABLE means the bill itself shows the problem (for example demand above
  contract demand). INDICATIVE means a what-if scenario whose size is an assumption
  (for example shifting 10% of peak energy); the assumption is stated.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from enum import Enum
from fractions import Fraction
from typing import Any

from samay.billing import (
    BillBreakdown,
    BillInput,
    BillValidationError,
    ZoneConsumption,
    recompute_bill,
)
from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    Money,
    Provenance,
    SamayCoreError,
    Traced,
)
from samay.tariffs import Tariff, TodZone

_MILLI = Decimal("0.001")  # quantities are held to 3 decimal places

# Stated assumptions for the what-if scenarios. They are deliberately modest.
DEMAND_REDUCTION_PERCENT = Decimal(10)
LOAD_SHIFT_PERCENT = Decimal(10)
CONTRACT_MARGIN_PERCENT = Decimal(10)
PF_TARGET = Decimal("0.99")
PF_FLAG_BELOW = Fraction(95, 100)
LOW_LOAD_FACTOR = Fraction(40, 100)
HIGH_PEAK_SHARE = Fraction(30, 100)


class Kind(Enum):
    ACTIONABLE = "actionable"
    INDICATIVE = "indicative"
    INFORMATION = "information"
    INSUFFICIENT_DATA = "insufficient-data"


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(Enum):
    PEAK_DEMAND = "peak-demand"
    CONTRACT_DEMAND = "contract-demand"
    LOAD_SHIFT = "load-shift"
    POWER_FACTOR = "power-factor"
    AVOIDABLE_CHARGES = "avoidable-charges"
    CONSUMPTION_PATTERN = "consumption-pattern"


class SavingStatus(Enum):
    ESTIMATED = "estimated"  # verified tariff, scenario recalculated by the bill engine
    ILLUSTRATIVE = "illustrative"  # synthetic tariff: shows the mechanism, not a real saving
    NOT_APPLICABLE = "not-applicable"  # nothing to save, or a qualitative finding
    INSUFFICIENT_DATA = "insufficient-data"


@dataclass(frozen=True, slots=True)
class Metric:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class Saving:
    """current - scenario, both totals recalculated by recompute_bill()."""

    status: SavingStatus
    note: str
    current_total: Money | None = None
    scenario_total: Money | None = None
    scenario: str | None = None

    @property
    def amount(self) -> Money | None:
        if self.current_total is None or self.scenario_total is None:
            return None
        return self.current_total - self.scenario_total


@dataclass(frozen=True, slots=True)
class Recommendation:
    key: str
    category: Category
    kind: Kind
    title: str
    finding: str  # what the bill shows
    action: str  # what to do about it
    confidence: Confidence
    confidence_reason: str
    saving: Saving
    metrics: tuple[Metric, ...] = ()
    basis: tuple[str, ...] = ()  # how it was worked out
    assumptions: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ZoneShare:
    zone: TodZone
    hours: str
    kvah: ApparentEnergy | None
    percent: str | None  # of total kVAh, 1 decimal place, display only


@dataclass(frozen=True, slots=True)
class Profile:
    """The consumption and demand data on the bill, for charts. MISSING stays None."""

    contract_demand_kva: ApparentPower | None
    recorded_md_kva: ApparentPower | None
    demand_floor_kva: str | None
    billing_demand_kva: str | None
    kwh: Any
    kvah: ApparentEnergy | None
    power_factor: str | None
    period_hours: str
    load_factor_percent: str | None
    zones: tuple[ZoneShare, ...]


@dataclass(frozen=True, slots=True)
class OptimisationReport:
    bill_id: str
    tariff_id: str
    tariff_status: DataStatus
    banner: str | None
    profile: Profile
    current_total: Money | None
    recommendations: tuple[Recommendation, ...]

    @property
    def synthetic(self) -> bool:
        return self.tariff_status is DataStatus.SYNTHETIC

    def count(self, kind: Kind) -> int:
        return sum(1 for r in self.recommendations if r.kind is kind)


# ---- helpers ---------------------------------------------------------------------


def _quantity(value: Traced[Any]) -> Any | None:
    return None if value.is_missing else value.value


def _milli(value: Decimal, rounding: str) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return value.quantize(_MILLI, rounding=rounding)


def _percent_text(part: Fraction) -> str:
    """A ratio as a percentage with one decimal place, for display only."""
    tenths = part * 1000
    whole, remainder = divmod(tenths.numerator, tenths.denominator)
    if 2 * remainder >= tenths.denominator:
        whole += 1
    return f"{whole // 10}.{whole % 10}%"


def _scenario_value[T](original: Traced[T], value: T, basis: str) -> Traced[T]:
    return Traced.estimated(value, basis=f"scenario: {basis}", status=original.status)


def _estimates(bill: BillInput) -> tuple[str, ...]:
    values: list[Traced[Any]] = [bill.contract_demand, bill.recorded_md, bill.kwh, bill.kvah]
    if bill.zones is not None:
        values.extend(v for _, v in bill.zones.items())
    return tuple(v.note for v in values if v.provenance is Provenance.ESTIMATED)


def _total(bill: BillInput, tariff: Tariff) -> BillBreakdown | None:
    try:
        return recompute_bill(bill, tariff)
    except (BillValidationError, SamayCoreError):
        return None


class _Analysis:
    def __init__(self, bill: BillInput, tariff: Tariff) -> None:
        self.bill = bill
        self.tariff = tariff
        self.current = _total(bill, tariff)
        self.estimates = _estimates(bill)

    @property
    def current_total(self) -> Money | None:
        if self.current is None or self.current.total.is_missing:
            return None
        return self.current.total.value

    def total_missing_reasons(self) -> tuple[str, ...]:
        if self.current is None:
            return ("the bill could not be recalculated",)
        return self.current.total.missing_reasons()

    def saving(self, scenario: str, changed: BillInput) -> Saving:
        current = self.current_total
        if current is None:
            reasons = "; ".join(self.total_missing_reasons())
            return Saving(
                SavingStatus.INSUFFICIENT_DATA,
                f"Insufficient data: the current bill total cannot be calculated ({reasons}).",
                scenario=scenario,
            )
        after = _total(changed, self.tariff)
        if after is None or after.total.is_missing:
            return Saving(
                SavingStatus.INSUFFICIENT_DATA,
                "Insufficient data: the scenario bill cannot be calculated.",
                scenario=scenario,
            )
        if self.tariff.is_synthetic:
            note = (
                f"Illustrative only: recalculated with {self.tariff.tariff_id}, a SYNTHETIC "
                "tariff. This shows how the saving arises; it is not a real-world saving."
            )
            status = SavingStatus.ILLUSTRATIVE
        elif after.total.status is DataStatus.SYNTHETIC:
            note = (
                "Illustrative only: the bill's readings are marked SYNTHETIC, so this is not "
                "a real-world saving."
            )
            status = SavingStatus.ILLUSTRATIVE
        else:
            note = f"Estimated by recalculating this bill with {self.tariff.tariff_id}."
            status = SavingStatus.ESTIMATED
        return Saving(status, note, current, after.total.value, scenario)

    def confidence(self, base: Confidence, reason: str) -> tuple[Confidence, str]:
        if self.estimates:
            lower = Confidence.MEDIUM if base is Confidence.HIGH else Confidence.LOW
            return lower, f"{reason} Lowered: it rests on estimated input(s): " + "; ".join(
                self.estimates
            )
        return base, reason

    # ---- demand ---------------------------------------------------------------------

    def demand(self) -> list[Recommendation]:
        bill, tariff = self.bill, self.tariff
        cd, md = _quantity(bill.contract_demand), _quantity(bill.recorded_md)
        missing = tuple(
            f"{what}: {'; '.join(value.missing_reasons())}"
            for what, value in (
                ("contract demand", bill.contract_demand),
                ("recorded maximum demand", bill.recorded_md),
            )
            if value.is_missing
        )
        if cd is None or md is None:
            return [
                Recommendation(
                    key="demand-insufficient",
                    category=Category.PEAK_DEMAND,
                    kind=Kind.INSUFFICIENT_DATA,
                    title="Peak demand: insufficient data",
                    finding="Contract demand and recorded maximum demand are both needed.",
                    action="Enter both values from the bill to analyse demand charges.",
                    confidence=Confidence.LOW,
                    confidence_reason="Required values are missing.",
                    saving=Saving(SavingStatus.INSUFFICIENT_DATA, "Insufficient data."),
                    missing_data=missing,
                )
            ]
        floor_percent = tariff.demand_floor_percent
        floor = cd.value * floor_percent / 100
        metrics = (
            Metric("Contract demand", f"{cd.value} kVA"),
            Metric("Recorded maximum demand", f"{md.value} kVA"),
            Metric(f"Demand floor ({floor_percent}% of contract)", f"{floor} kVA"),
            # contract demand is never 0: validation refuses it
            Metric("Utilisation of contract demand", _percent_text(Fraction(md.value / cd.value))),
        )
        out: list[Recommendation] = []
        if md > cd:
            excess = md - cd
            changed = dataclasses.replace(
                bill,
                recorded_md=_scenario_value(
                    bill.recorded_md,
                    ApparentPower(cd.value),
                    "maximum demand kept at contract demand",
                ),
            )
            conf, why = self.confidence(
                Confidence.HIGH, "Both values are read from the bill; the excess is measured."
            )
            out.append(
                Recommendation(
                    key="excess-demand",
                    category=Category.PEAK_DEMAND,
                    kind=Kind.ACTIONABLE,
                    title="Avoid the excess demand penalty",
                    finding=(
                        f"Maximum demand {md.value} kVA exceeded the contract demand of "
                        f"{cd.value} kVA by {excess.value} kVA, which triggers the excess "
                        f"demand charge ({tariff.excess_demand_multiplier}x the demand rate)."
                    ),
                    action=(
                        "Stagger the start of large loads (compressors, furnaces, motors) so the "
                        "15-minute peak stays below contract demand, or review the contract "
                        "demand with the utility if this peak is routine."
                    ),
                    confidence=conf,
                    confidence_reason=why,
                    saving=self.saving(f"maximum demand held at {cd.value} kVA", changed),
                    metrics=(*metrics, Metric("Excess demand", f"{excess.value} kVA")),
                    basis=(
                        "Scenario: the same bill with recorded maximum demand equal to "
                        "contract demand, recalculated with the same tariff.",
                        "Saving = current total - scenario total (includes demand, excess "
                        "demand, duty and rounding).",
                    ),
                )
            )
        elif md.value > floor:
            target = max(
                _milli(md.value * (100 - DEMAND_REDUCTION_PERCENT) / 100, ROUND_FLOOR), floor
            )
            target = _milli(target, ROUND_CEILING)
            changed = dataclasses.replace(
                bill,
                recorded_md=_scenario_value(
                    bill.recorded_md,
                    ApparentPower(target),
                    f"maximum demand {DEMAND_REDUCTION_PERCENT}% lower",
                ),
            )
            conf, why = self.confidence(
                Confidence.MEDIUM,
                "The demand data is measured, but the achievable reduction is an assumption.",
            )
            out.append(
                Recommendation(
                    key="peak-shaving",
                    category=Category.PEAK_DEMAND,
                    kind=Kind.INDICATIVE,
                    title="Shave the monthly demand peak",
                    finding=(
                        f"Maximum demand {md.value} kVA sets the demand charge (it is above the "
                        f"{floor} kVA floor). Every kVA shaved off the single highest 15-minute "
                        "peak lowers the demand charge."
                    ),
                    action=(
                        "Find the hour of the monthly peak from the meter's load survey and "
                        "avoid running the largest loads together at that time."
                    ),
                    confidence=conf,
                    confidence_reason=why,
                    saving=self.saving(f"maximum demand reduced to {target} kVA", changed),
                    metrics=metrics,
                    basis=(
                        f"Scenario: maximum demand {DEMAND_REDUCTION_PERCENT}% lower ({target} "
                        "kVA, not below the demand floor), recalculated with the same tariff.",
                    ),
                    assumptions=(
                        f"A {DEMAND_REDUCTION_PERCENT}% lower peak is assumed to be achievable "
                        "by rescheduling; the bill has no 15-minute load data to confirm it.",
                    ),
                )
            )
        if md.value < floor:
            margin = md.value * (100 + CONTRACT_MARGIN_PERCENT) / 100
            new_cd = (margin * 100 / floor_percent).to_integral_value(rounding=ROUND_CEILING)
            if new_cd < cd.value:
                changed = dataclasses.replace(
                    bill,
                    contract_demand=_scenario_value(
                        bill.contract_demand,
                        ApparentPower(new_cd),
                        f"contract demand revised to {new_cd} kVA",
                    ),
                )
                conf, why = self.confidence(
                    Confidence.MEDIUM,
                    "Measured on one bill; a contract change should rest on 12 months of peaks.",
                )
                out.append(
                    Recommendation(
                        key="contract-demand",
                        category=Category.CONTRACT_DEMAND,
                        kind=Kind.INDICATIVE,
                        title="Contract demand may be oversized",
                        finding=(
                            f"Maximum demand {md.value} kVA is below the billing floor of "
                            f"{floor} kVA ({floor_percent}% of {cd.value} kVA), so demand that "
                            "was never used is being paid for."
                        ),
                        action=(
                            "Check the last 12 months of maximum demand. If peaks stay this low, "
                            f"apply to reduce contract demand (for example to {new_cd} kVA)."
                        ),
                        confidence=conf,
                        confidence_reason=why,
                        saving=self.saving(f"contract demand {new_cd} kVA", changed),
                        metrics=metrics,
                        basis=(
                            f"Scenario: contract demand {new_cd} kVA, the smallest whole kVA whose "
                            f"floor covers this peak plus a {CONTRACT_MARGIN_PERCENT}% margin.",
                        ),
                        assumptions=(
                            "Future peaks stay within the margin; one bill is not enough to "
                            "decide a contract change.",
                        ),
                    )
                )
        return out

    # ---- time of day ------------------------------------------------------------------

    def load_shift(self) -> Recommendation:
        bill, tariff = self.bill, self.tariff
        zones = bill.zones
        if zones is None or not zones.is_complete:
            reasons = (
                ("no time-of-day zone readings on the bill",)
                if zones is None
                else tuple(
                    f"{zone.value} zone: {'; '.join(value.missing_reasons())}"
                    for zone, value in zones.items()
                    if value.is_missing
                )
            )
            return Recommendation(
                key="load-shift",
                category=Category.LOAD_SHIFT,
                kind=Kind.INSUFFICIENT_DATA,
                title="Load shifting: insufficient data",
                finding="Shifting needs the peak, normal and off-peak kVAh from the meter.",
                action="Enter all three time-of-day zone readings printed on the bill.",
                confidence=Confidence.LOW,
                confidence_reason="Zone readings are missing.",
                saving=Saving(SavingStatus.INSUFFICIENT_DATA, "Insufficient data."),
                missing_data=reasons,
            )
        peak = zones.peak.value
        off_peak = zones.off_peak.value
        peak_rate = tariff.tod_rate(TodZone.PEAK).paise_per_unit
        off_rate = tariff.tod_rate(TodZone.OFF_PEAK).paise_per_unit
        hours = {t.zone: t.hours for t in tariff.tod_rates}
        total = _quantity(bill.kvah)
        share = None
        if total is not None and total.value:
            share = Fraction(peak.value) / Fraction(total.value)
        metrics = (
            *(
                Metric(
                    f"{zone.value.replace('_', '-')} ({hours[zone]})",
                    f"{value.value.value} kVAh"
                    + (
                        f" ({_percent_text(Fraction(value.value.value) / Fraction(total.value))})"
                        if total is not None and total.value
                        else ""
                    ),
                )
                for zone, value in zones.items()
            ),
            Metric("Peak minus off-peak rate", f"{peak_rate - off_rate} paise/kVAh"),
        )
        if peak.value == 0 or peak_rate <= off_rate:
            return Recommendation(
                key="load-shift",
                category=Category.LOAD_SHIFT,
                kind=Kind.INFORMATION,
                title="No time-of-day saving to make",
                finding=(
                    "No energy was used in the peak zone."
                    if peak.value == 0
                    else "This tariff does not charge more in peak hours than off-peak."
                ),
                action="No action needed.",
                confidence=Confidence.HIGH,
                confidence_reason="Read from the bill and the tariff.",
                saving=Saving(SavingStatus.NOT_APPLICABLE, "Nothing to save."),
                metrics=metrics,
            )
        moved = _milli(peak.value * LOAD_SHIFT_PERCENT / 100, ROUND_FLOOR)
        changed = dataclasses.replace(
            bill,
            zones=ZoneConsumption(
                peak=_scenario_value(
                    zones.peak, ApparentEnergy(peak.value - moved), "peak energy shifted"
                ),
                off_peak=_scenario_value(
                    zones.off_peak, ApparentEnergy(off_peak.value + moved), "peak energy shifted"
                ),
                normal=zones.normal,
            ),
        )
        conf, why = self.confidence(
            Confidence.MEDIUM,
            "Zone readings are from the bill; how much load can move is an assumption.",
        )
        kind = Kind.INDICATIVE
        title = "Shift flexible load out of peak hours"
        if share is not None and share >= HIGH_PEAK_SHARE:
            title = "High peak-hour consumption: shift flexible load"
        return Recommendation(
            key="load-shift",
            category=Category.LOAD_SHIFT,
            kind=kind,
            title=title,
            finding=(
                f"{peak.value} kVAh"
                + (f" ({_percent_text(share)} of the month)" if share is not None else "")
                + f" was used in peak hours ({hours[TodZone.PEAK]}), which cost "
                f"{peak_rate - off_rate} paise/kVAh more than off-peak ({hours[TodZone.OFF_PEAK]})."
            ),
            action=(
                "Move batch processes, water pumping, chilling or charging that can run at "
                "night into the off-peak window."
            ),
            confidence=conf,
            confidence_reason=why,
            saving=self.saving(f"{moved} kVAh moved from peak to off-peak", changed),
            metrics=metrics,
            basis=(
                f"Scenario: {LOAD_SHIFT_PERCENT}% of peak energy ({moved} kVAh) moved to "
                "off-peak, total energy unchanged, recalculated with the same tariff.",
            ),
            assumptions=(
                f"{LOAD_SHIFT_PERCENT}% of peak-hour energy is assumed to be flexible. The "
                "bill does not show which loads run at peak.",
            ),
        )

    # ---- power factor -----------------------------------------------------------------

    def power_factor(self) -> Recommendation:
        bill = self.bill
        kwh, kvah = _quantity(bill.kwh), _quantity(bill.kvah)
        if kwh is None or kvah is None or kvah.value == 0:
            return Recommendation(
                key="power-factor",
                category=Category.POWER_FACTOR,
                kind=Kind.INSUFFICIENT_DATA,
                title="Power factor: insufficient data",
                finding="Power factor needs both kWh and kVAh for the same period.",
                action="Enter kWh and kVAh from the bill.",
                confidence=Confidence.LOW,
                confidence_reason="Required values are missing.",
                saving=Saving(SavingStatus.INSUFFICIENT_DATA, "Insufficient data."),
                missing_data=tuple(
                    f"{what}: {'; '.join(v.missing_reasons()) or 'zero'}"
                    for what, v in (("kWh", bill.kwh), ("kVAh", bill.kvah))
                    if v.is_missing or v.value.value == 0
                ),
            )
        pf = Fraction(kwh.value) / Fraction(kvah.value)
        shown = f"{_percent_text(pf)[:-1]}"  # e.g. 91.7 (percent)
        pf_text = f"{Decimal(pf.numerator) / Decimal(pf.denominator):.3f}"
        metrics = (
            Metric("Average power factor", pf_text),
            Metric("Active energy", f"{kwh.value} kWh"),
            Metric("Apparent energy (billed)", f"{kvah.value} kVAh"),
        )
        if pf >= PF_FLAG_BELOW:
            return Recommendation(
                key="power-factor",
                category=Category.POWER_FACTOR,
                kind=Kind.INFORMATION,
                title="Power factor is healthy",
                finding=f"Average power factor is {pf_text} ({shown}%).",
                action="Keep capacitor banks maintained.",
                confidence=Confidence.HIGH,
                confidence_reason="Calculated from kWh and kVAh on the bill.",
                saving=Saving(SavingStatus.NOT_APPLICABLE, "Nothing material to save."),
                metrics=metrics,
            )
        new_kvah = _milli(kwh.value / PF_TARGET, ROUND_CEILING)
        changes: dict[str, Any] = {
            "kvah": _scenario_value(
                bill.kvah, ApparentEnergy(new_kvah), f"power factor raised to {PF_TARGET}"
            )
        }
        zones = bill.zones
        if zones is not None and zones.is_complete:
            scale = new_kvah / kvah.value
            peak = _milli(zones.peak.value.value * scale, ROUND_FLOOR)
            off = _milli(zones.off_peak.value.value * scale, ROUND_FLOOR)
            normal = new_kvah - peak - off
            basis = f"zones scaled with power factor {PF_TARGET}"
            changes["zones"] = ZoneConsumption(
                peak=_scenario_value(zones.peak, ApparentEnergy(peak), basis),
                off_peak=_scenario_value(zones.off_peak, ApparentEnergy(off), basis),
                normal=_scenario_value(zones.normal, ApparentEnergy(normal), basis),
            )
        changed = dataclasses.replace(bill, **changes)
        conf, why = self.confidence(
            Confidence.MEDIUM,
            "Power factor is calculated from the bill; reaching the target needs correctly "
            "sized capacitors.",
        )
        return Recommendation(
            key="power-factor",
            category=Category.POWER_FACTOR,
            kind=Kind.ACTIONABLE,
            title="Raise power factor to cut billed kVAh",
            finding=(
                f"Average power factor is {pf_text}. Energy is billed on kVAh, so every unit of "
                f"reactive power is paid for: {kvah.value} kVAh were billed for {kwh.value} kWh "
                "of useful energy."
            ),
            action=(
                "Install or repair automatic power factor correction (capacitor banks) near "
                f"inductive loads to bring power factor to {PF_TARGET}."
            ),
            confidence=conf,
            confidence_reason=why,
            saving=self.saving(f"power factor {PF_TARGET} ({new_kvah} kVAh)", changed),
            metrics=(*metrics, Metric(f"kVAh at power factor {PF_TARGET}", f"{new_kvah} kVAh")),
            basis=(
                f"Scenario: the same kWh at power factor {PF_TARGET} (kVAh = kWh / {PF_TARGET}, "
                "rounded up to 0.001), each zone scaled in proportion, recalculated with the "
                "same tariff.",
            ),
            assumptions=(
                f"Power factor {PF_TARGET} is a common target for automatic correction; the "
                "capacitor cost is not included.",
            ),
        )

    # ---- charges and pattern ----------------------------------------------------------

    def charges(self) -> list[Recommendation]:
        out: list[Recommendation] = []
        others = self.bill.pass_through_lines
        if others:
            out.append(
                Recommendation(
                    key="other-charges",
                    category=Category.AVOIDABLE_CHARGES,
                    kind=Kind.INFORMATION,
                    title="Review charges SAMAY cannot check",
                    finding=(
                        "These lines were taken as printed, not recalculated: "
                        + ", ".join(
                            f"{line.label} "
                            + (
                                "MISSING"
                                if line.amount.is_missing
                                else line.amount.value.format_inr()
                            )
                            for line in others
                        )
                        + "."
                    ),
                    action=(
                        "Check each against the tariff order and your agreement with the "
                        "utility (for example meter rent for a meter you own)."
                    ),
                    confidence=Confidence.LOW,
                    confidence_reason="The tariff rules for these lines are not modelled.",
                    saving=Saving(
                        SavingStatus.INSUFFICIENT_DATA,
                        "Insufficient data: no tariff rule for these charges.",
                    ),
                )
            )
        return out

    def pattern(self, profile: Profile) -> list[Recommendation]:
        out: list[Recommendation] = []
        if profile.load_factor_percent is not None and self._load_factor is not None:
            low = self._load_factor < LOW_LOAD_FACTOR
            out.append(
                Recommendation(
                    key="load-factor",
                    category=Category.CONSUMPTION_PATTERN,
                    kind=Kind.INDICATIVE if low else Kind.INFORMATION,
                    title="Peaky load profile" if low else "Steady load profile",
                    finding=(
                        f"Load factor is {profile.load_factor_percent}: average apparent load "
                        "over the period compared with the maximum demand."
                        + (
                            " A low load factor means short, high peaks relative to the "
                            "average, which drive the demand charge."
                            if low
                            else ""
                        )
                    ),
                    action=(
                        "Spread high loads more evenly across shifts."
                        if low
                        else "No action needed."
                    ),
                    confidence=Confidence.MEDIUM,
                    confidence_reason="Uses monthly totals; interval data would show the peaks.",
                    saving=Saving(
                        SavingStatus.NOT_APPLICABLE,
                        "Not priced: shown to explain the demand charge.",
                    ),
                    basis=("Load factor = kVAh / (maximum demand kVA x hours in the period).",),
                )
            )
        out.append(
            Recommendation(
                key="trend",
                category=Category.CONSUMPTION_PATTERN,
                kind=Kind.INSUFFICIENT_DATA,
                title="Unusual consumption: insufficient data",
                finding="Spotting unusual consumption needs earlier bills for the same meter.",
                action=(
                    f"Save at least three months of bills for meter {self.bill.period.meter_id} "
                    "to compare."
                ),
                confidence=Confidence.LOW,
                confidence_reason="One bill has no baseline.",
                saving=Saving(SavingStatus.INSUFFICIENT_DATA, "Insufficient data."),
                missing_data=("earlier bills for the same meter",),
            )
        )
        return out

    # ---- profile ---------------------------------------------------------------------

    _load_factor: Fraction | None = None

    def profile(self) -> Profile:
        bill, tariff = self.bill, self.tariff
        cd, md = _quantity(bill.contract_demand), _quantity(bill.recorded_md)
        kwh, kvah = _quantity(bill.kwh), _quantity(bill.kvah)
        seconds = Fraction(int((bill.period.end - bill.period.start).total_seconds()))
        hours = seconds / 3600
        hours_text = (
            str(hours.numerator)
            if hours.denominator == 1
            else f"{Decimal(hours.numerator) / Decimal(hours.denominator):.2f}"
        )
        load_factor = None
        if md is not None and kvah is not None and md.value and hours:
            self._load_factor = Fraction(kvah.value) / (Fraction(md.value) * hours)
            load_factor = _percent_text(self._load_factor)
        pf = None
        if kwh is not None and kvah is not None and kvah.value:
            ratio = Fraction(kwh.value) / Fraction(kvah.value)
            pf = f"{Decimal(ratio.numerator) / Decimal(ratio.denominator):.3f}"
        floor = None if cd is None else str(cd.value * tariff.demand_floor_percent / 100)
        billing = None
        if self.current is not None:
            try:
                quantity = self.current.quantity("billing_demand").value
                billing = None if quantity.is_missing else str(quantity.value.value)
            except KeyError:  # pragma: no cover - the engine always reports it
                billing = None
        zones: list[ZoneShare] = []
        hours_by_zone = {t.zone: t.hours for t in tariff.tod_rates}
        for zone in TodZone:
            value = None if bill.zones is None else _quantity(bill.zones.of(zone))
            percent = (
                _percent_text(Fraction(value.value) / Fraction(kvah.value))
                if value is not None and kvah is not None and kvah.value
                else None
            )
            zones.append(ZoneShare(zone, hours_by_zone[zone], value, percent))
        return Profile(
            contract_demand_kva=cd,
            recorded_md_kva=md,
            demand_floor_kva=floor,
            billing_demand_kva=billing,
            kwh=kwh,
            kvah=kvah,
            power_factor=pf,
            period_hours=hours_text,
            load_factor_percent=load_factor,
            zones=tuple(zones),
        )


def optimise(bill: BillInput, tariff: Tariff) -> OptimisationReport:
    """Explainable cost-reduction opportunities for one bill."""
    if not isinstance(bill, BillInput):
        raise TypeError("optimise() needs a BillInput")
    if not isinstance(tariff, Tariff):
        raise TypeError("optimise() needs a Tariff")
    analysis = _Analysis(bill, tariff)
    profile = analysis.profile()
    recommendations = [
        *analysis.demand(),
        analysis.power_factor(),
        analysis.load_shift(),
        *analysis.charges(),
        *analysis.pattern(profile),
    ]
    order = {Kind.ACTIONABLE: 0, Kind.INDICATIVE: 1, Kind.INFORMATION: 2, Kind.INSUFFICIENT_DATA: 3}
    recommendations.sort(key=lambda r: order[r.kind])
    return OptimisationReport(
        bill_id=bill.bill_id,
        tariff_id=tariff.tariff_id,
        tariff_status=tariff.status,
        banner=analysis.current.banner if analysis.current is not None else None,
        profile=profile,
        current_total=analysis.current_total,
        recommendations=tuple(recommendations),
    )


__all__ = [
    "Category",
    "Confidence",
    "Kind",
    "Metric",
    "OptimisationReport",
    "Profile",
    "Recommendation",
    "Saving",
    "SavingStatus",
    "ZoneShare",
    "optimise",
]
