"""Recalculate one bill from meter readings and a tariff (SAMAY-DEMO-1 shape, D3).

Order of work (C1..C9 in docs/tariffs/SAMAY-DEMO-1.md):

C1 billing demand  = max(MD, floor% x CD), exact, never rounded
C2 demand charge   = demand rate x billing demand
C3 excess demand   = max(MD - CD, 0) x demand rate x multiplier
C4 energy charge   = energy rate x kVAh
C5 ToD adjustment  = sum over zones of zone rate x zone kVAh, rounded once
C6 duty            = duty% x (rounded C2 + C3 + C4 + C5)
C7 printed 'other' lines, taken as printed
C8 subtotal        = C2 + ... + C7 (not a line)
C9 rounding off    = total rounding(C8) - C8
total              = C8 + C9 = the sum of all money lines

Each of C2..C6 is computed exactly and rounded once with the tariff's
line rule. A MISSING input makes the lines that need it MISSING, and then the
subtotal, rounding off and total too; nothing is ever treated as zero.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    Energy,
    ExactAmount,
    ExactApparentPower,
    IntervalReading,
    Money,
    PowerFactor,
    QuantityRounding,
    Rate,
    SamayCoreError,
    Traced,
    average_power_factor,
    combine_status,
)
from samay.tariffs import ComponentCode, Tariff, TodZone

from .breakdown import BillBreakdown, LineBasis, MoneyLine, QuantityLine
from .inputs import BillInput
from .validation import BillValidationError, Severity, validate_bill


class BillInvariantError(SamayCoreError, AssertionError):
    """An internal consistency check failed. This is a bug in SAMAY, not in the input."""


def _show(value: Traced[Any]) -> str:
    return "MISSING" if value.is_missing else str(value.value)


def _sum(*amounts: Money) -> Money:
    return sum(amounts, Money.zero())


def recompute_bill(bill: BillInput, tariff: Tariff) -> BillBreakdown:
    """The full breakdown, or BillValidationError if the input has errors."""
    issues = validate_bill(bill, tariff)
    errors = tuple(i for i in issues if i.severity is Severity.ERROR)
    if errors:
        raise BillValidationError(errors)
    return _Calculation(bill, tariff).breakdown(issues)


class _Calculation:
    def __init__(self, bill: BillInput, tariff: Tariff) -> None:
        self.bill = bill
        self.tariff = tariff
        self.quantities: list[QuantityLine] = []

    # ---- helpers -----------------------------------------------------------

    def param[T](self, value: T, code: ComponentCode, what: str) -> Traced[T]:
        """A tariff parameter as a traced value, labelled with its source."""
        return Traced.extracted(
            value, source=f"{self.tariff.source_note(code)} ({what})", status=self.tariff.status
        )

    def money_line(
        self,
        code: ComponentCode,
        exact: Traced[ExactAmount],
        formula: str,
    ) -> MoneyLine:
        rule = self.tariff.line_rounding
        terms = self.tariff.terms(code)

        def round_once(amount: ExactAmount) -> Money:
            return amount.round(rule)

        amount = Traced.derive(round_once, exact, description=f"{terms.label}, {rule.value}")
        return MoneyLine(
            code=code,
            label=terms.label,
            basis=LineBasis.RECALCULATED,
            amount=amount,
            exact=exact,
            rounding=rule,
            formula=formula,
            assumptions=terms.assumptions,
        )

    def add_quantity(self, key: str, label: str, value: Traced[Any], formula: str) -> None:
        self.quantities.append(QuantityLine(key, label, value, formula))

    # ---- components --------------------------------------------------------

    def billing_demand(self) -> Traced[ExactApparentPower]:  # C1
        bill, tariff = self.bill, self.tariff
        code = ComponentCode.DEMAND_CHARGE
        floor_percent = self.param(tariff.demand_floor_percent, code, "demand floor %")

        def floor(cd: ApparentPower, percent: Any) -> ExactApparentPower:
            return cd.percent(percent)

        demand_floor = Traced.derive(
            floor,
            bill.contract_demand,
            floor_percent,
            description=f"demand floor: {tariff.demand_floor_percent}% of contract demand",
        )
        self.add_quantity(
            "demand_floor",
            "Demand floor",
            demand_floor,
            f"{tariff.demand_floor_percent}% x contract demand {_show(bill.contract_demand)}"
            f" = {_show(demand_floor)}",
        )

        def higher(md: ApparentPower, minimum: ExactApparentPower) -> ExactApparentPower:
            measured = ExactApparentPower.from_measured(md)
            return measured if measured >= minimum else minimum

        result = Traced.derive(
            higher,
            bill.recorded_md,
            demand_floor,
            description="billing demand: higher of recorded MD and demand floor",
        )
        self.add_quantity(
            "billing_demand",
            "Billing demand",
            result,
            f"max(recorded MD {_show(bill.recorded_md)}, demand floor {_show(demand_floor)})"
            f" = {_show(result)}",
        )
        return result

    def demand_charge(self, billing_demand: Traced[ExactApparentPower]) -> MoneyLine:  # C2
        code = ComponentCode.DEMAND_CHARGE
        rate = self.param(self.tariff.demand_rate, code, "demand rate")

        def charge(r: Rate, demand: ExactApparentPower) -> ExactAmount:
            return r * demand

        exact = Traced.derive(charge, rate, billing_demand, description="demand charge, exact")
        return self.money_line(
            code,
            exact,
            f"{self.tariff.demand_rate.format_inr()} x billing demand {_show(billing_demand)}"
            f" = {_exact(exact)}",
        )

    def excess_demand_charge(self) -> MoneyLine:  # C3
        bill, tariff = self.bill, self.tariff
        code = ComponentCode.EXCESS_DEMAND_CHARGE

        def excess(md: ApparentPower, cd: ApparentPower) -> ApparentPower:
            return md - cd if md > cd else ApparentPower.zero()

        excess_kva = Traced.derive(
            excess,
            bill.recorded_md,
            bill.contract_demand,
            description="excess demand: recorded MD above contract demand",
        )
        self.add_quantity(
            "excess_demand",
            "Excess demand",
            excess_kva,
            f"max(recorded MD {_show(bill.recorded_md)} - contract demand "
            f"{_show(bill.contract_demand)}, 0) = {_show(excess_kva)}",
        )
        rate = self.param(tariff.demand_rate, code, "demand rate")
        multiplier = self.param(tariff.excess_demand_multiplier, code, "excess multiplier")

        def charge(kva: ApparentPower, r: Rate, times: Any) -> ExactAmount:
            return r.scaled(times) * kva

        exact = Traced.derive(
            charge, excess_kva, rate, multiplier, description="excess demand charge, exact"
        )
        return self.money_line(
            code,
            exact,
            f"excess demand {_show(excess_kva)} x {tariff.demand_rate.format_inr()} x "
            f"{tariff.excess_demand_multiplier} = {_exact(exact)}",
        )

    def energy_charge(self) -> MoneyLine:  # C4
        code = ComponentCode.ENERGY_CHARGE
        rate = self.param(self.tariff.energy_rate, code, "energy rate")

        def charge(r: Rate, kvah: ApparentEnergy) -> ExactAmount:
            return r * kvah

        exact = Traced.derive(charge, rate, self.bill.kvah, description="energy charge, exact")
        return self.money_line(
            code,
            exact,
            f"{self.tariff.energy_rate.format_inr()} x {_show(self.bill.kvah)} = {_exact(exact)}",
        )

    def tod_adjustment(self) -> MoneyLine:  # C5
        bill, tariff = self.bill, self.tariff
        code = ComponentCode.TOD_ADJUSTMENT
        if bill.zones is None:
            # Missing, never zero: without zone readings the adjustment is unknown.
            no_zones: Traced[ExactAmount] = Traced.missing(
                reason="ToD zone readings not provided",
                status=combine_status((tariff.status, bill.kvah.status)),
                kind=ExactAmount,
            )
            return self.money_line(code, no_zones, "zone readings MISSING")
        zones = tuple(TodZone)
        zone_values = tuple(bill.zones.of(zone) for zone in zones)
        for zone, value in zip(zones, zone_values, strict=True):
            self.add_quantity(f"kvah_{zone.value}", f"kVAh, {zone.value} zone", value, "read")
        rates = tuple(self.param(tariff.tod_rate(z), code, f"{z.value} rate") for z in zones)

        def adjustment(*values: Any) -> ExactAmount:
            # values = zone kVAh..., then zone rates...; added exactly, rounded once later.
            count = len(values) // 2
            total = ExactAmount(Decimal(0))
            for kvah, rate in zip(values[:count], values[count:], strict=True):
                total = total + rate * kvah
            return total

        exact = Traced.derive(
            adjustment, *zone_values, *rates, description="ToD adjustment, exact sum of zones"
        )
        terms = " + ".join(
            f"{_show(v)} x {tariff.tod_rate(z).format_inr()}"
            for z, v in zip(zones, zone_values, strict=True)
        )
        return self.money_line(code, exact, f"{terms} = {_exact(exact)}")

    def duty(self, base_lines: tuple[MoneyLine, ...]) -> MoneyLine:  # C6
        code = ComponentCode.ELECTRICITY_DUTY
        percent = self.param(self.tariff.duty_percent, code, "duty %")

        def duty_of(rate: Any, *amounts: Money) -> ExactAmount:
            return _sum(*amounts).percent_exact(rate)

        exact = Traced.derive(
            duty_of,
            percent,
            *(line.amount for line in base_lines),
            description="electricity duty, exact",
        )
        names = " + ".join(_show(line.amount) for line in base_lines)
        return self.money_line(
            code, exact, f"{self.tariff.duty_percent}% x ({names}) = {_exact(exact)}"
        )

    def pass_through(self) -> tuple[MoneyLine, ...]:  # C7
        return tuple(
            MoneyLine(
                code=line.code,
                label=line.label,
                basis=LineBasis.NOT_RECALCULATED,
                amount=line.amount,
                exact=None,
                rounding=None,
                formula="taken as printed, not recalculated",
                assumptions=(),
            )
            for line in self.bill.pass_through_lines
        )

    def power_factor(self) -> None:
        """Average power factor, for information only (never charged)."""
        bill = self.bill

        def pf(kwh: Energy, kvah: ApparentEnergy) -> PowerFactor:
            return average_power_factor(
                IntervalReading(kwh, bill.period), IntervalReading(kvah, bill.period)
            )

        if not bill.kwh.is_missing and not bill.kvah.is_missing and bill.kvah.value.value == 0:
            value: Traced[Any] = Traced.missing(
                reason="kVAh is 0, so there is no power factor",
                status=combine_status((bill.kwh.status, bill.kvah.status)),
            )
        else:
            value = Traced.derive(pf, bill.kwh, bill.kvah, description="average power factor")
        shown = (
            "MISSING"
            if value.is_missing
            else f"{value.value.rounded(3, rounding=QuantityRounding.HALF_UP)} "
            "(shown to 3 places, half-up)"
        )
        self.add_quantity(
            "power_factor",
            "Average power factor (information only)",
            value,
            f"kWh {_show(bill.kwh)} / kVAh {_show(bill.kvah)} = {shown}",
        )

    # ---- assembly ----------------------------------------------------------

    def breakdown(self, issues: tuple[Any, ...]) -> BillBreakdown:
        bill, tariff = self.bill, self.tariff
        for key, label, value in (
            ("contract_demand", "Contract demand", bill.contract_demand),
            ("recorded_md", "Recorded maximum demand", bill.recorded_md),
            ("kwh", "Active energy", bill.kwh),
            ("kvah", "Apparent energy", bill.kvah),
        ):
            self.add_quantity(key, label, value, "read")

        billing_demand = self.billing_demand()
        c2 = self.demand_charge(billing_demand)
        c3 = self.excess_demand_charge()
        c4 = self.energy_charge()
        c5 = self.tod_adjustment()
        c6 = self.duty((c2, c3, c4, c5))
        c7 = self.pass_through()
        self.power_factor()
        charges = (c2, c3, c4, c5, c6, *c7)

        subtotal = Traced.derive(
            _sum, *(line.amount for line in charges), description="subtotal of all charges"
        )
        total_rule = tariff.total_rounding

        def rounding_off(amount: Money) -> Money:
            return amount.to_exact().round(total_rule) - amount

        c9_amount = Traced.derive(
            rounding_off, subtotal, description=f"rounding off: {total_rule.value} minus subtotal"
        )
        c9_terms = tariff.terms(ComponentCode.ROUNDING_OFF)
        c9 = MoneyLine(
            code=ComponentCode.ROUNDING_OFF,
            label=c9_terms.label,
            basis=LineBasis.RECALCULATED,
            amount=c9_amount,
            exact=None,
            rounding=total_rule,
            formula=f"{total_rule.value}({_show(subtotal)}) - {_show(subtotal)}"
            f" = {_show(c9_amount)}",
            assumptions=c9_terms.assumptions,
        )
        total = Traced.derive(
            _sum,
            *(line.amount for line in (*charges, c9)),
            description="payable total: sum of all money lines",
        )
        if not total.is_missing:
            rounded_subtotal = subtotal.value.to_exact().round(total_rule)
            if total.value != rounded_subtotal or total.value != subtotal.value + c9_amount.value:
                raise BillInvariantError(  # pragma: no cover - would be a SAMAY bug
                    f"total {total.value} != rounded subtotal {rounded_subtotal}"
                )

        banner = None
        if tariff.status is DataStatus.SYNTHETIC:
            banner = (
                f"{tariff.tariff_id} is SYNTHETIC: its rates are made up and are not UP tariff "
                "rates. This is not a real bill."
            )
        assumptions = list(tariff.assumptions)
        for line in (*charges, c9):
            for assumption in line.assumptions:
                if assumption not in assumptions:
                    assumptions.append(assumption)
        return BillBreakdown(
            bill_id=bill.bill_id,
            tariff_id=tariff.tariff_id,
            tariff_name=tariff.name,
            tariff_status=tariff.status,
            banner=banner,
            quantities=tuple(self.quantities),
            charges=charges,
            subtotal=subtotal,
            rounding_off=c9,
            total=total,
            assumptions=tuple(assumptions),
            issues=issues,
        )


def _exact(value: Traced[ExactAmount]) -> str:
    return "MISSING" if value.is_missing else value.value.format_inr()
