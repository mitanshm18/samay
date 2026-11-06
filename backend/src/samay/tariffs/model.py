"""Typed tariff definitions (decision 0003, D2).

A Tariff is plain, immutable data: rates as exact Rate values, percentages as
exact Decimals, and the rounding rules it uses, named explicitly. Every
component carries the assumption it rests on and, for a VERIFIED tariff, the
place in the tariff order it was taken from. Nothing here calculates a bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from samay.core import DataStatus, Rate, RateBasis, RoundingRule, SamayCoreError, Unit
from samay.core._decimal import DecimalInput, check_places, to_decimal


class TariffError(SamayCoreError, ValueError):
    """A tariff definition is incomplete or inconsistent, or is not known."""


class ComponentCode(Enum):
    """The bill lines SAMAY knows about. Printed lines are tagged with one of these."""

    DEMAND_CHARGE = "demand_charge"
    EXCESS_DEMAND_CHARGE = "excess_demand_charge"
    ENERGY_CHARGE = "energy_charge"
    TOD_ADJUSTMENT = "tod_adjustment"
    ELECTRICITY_DUTY = "electricity_duty"
    ROUNDING_OFF = "rounding_off"
    OTHER = "other"  # printed lines SAMAY does not recalculate (taken as printed)


CALCULATED_CODES: tuple[ComponentCode, ...] = (
    ComponentCode.DEMAND_CHARGE,
    ComponentCode.EXCESS_DEMAND_CHARGE,
    ComponentCode.ENERGY_CHARGE,
    ComponentCode.TOD_ADJUSTMENT,
    ComponentCode.ELECTRICITY_DUTY,
    ComponentCode.ROUNDING_OFF,
)


class TodZone(Enum):
    PEAK = "peak"
    OFF_PEAK = "off_peak"
    NORMAL = "normal"


def _text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TariffError(f"{what} must be non-empty text")
    return value


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where in a tariff order a value comes from, e.g. ('UPERC order 2025-26', 'p. 41, cl. 3')."""

    document: str
    location: str

    def __post_init__(self) -> None:
        _text(self.document, "SourceRef.document")
        _text(self.location, "SourceRef.location")

    def __str__(self) -> str:
        return f"{self.document}, {self.location}"


@dataclass(frozen=True, slots=True)
class Assumption:
    """An assumption a calculation rests on, stated as data so reports can show it."""

    key: str
    text: str

    def __post_init__(self) -> None:
        _text(self.key, "Assumption.key")
        _text(self.text, "Assumption.text")

    def __str__(self) -> str:
        return f"[{self.key}] {self.text}"


@dataclass(frozen=True, slots=True)
class ComponentTerms:
    """The label, assumptions and source of one calculated component."""

    code: ComponentCode
    label: str
    assumptions: tuple[Assumption, ...]
    source: SourceRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ComponentCode) or self.code is ComponentCode.OTHER:
            raise TariffError("ComponentTerms.code must be a calculated ComponentCode")
        _text(self.label, "ComponentTerms.label")
        if not isinstance(self.assumptions, tuple) or not all(
            isinstance(a, Assumption) for a in self.assumptions
        ):
            raise TariffError(f"{self.code.value}: assumptions must be a tuple of Assumption")
        if self.source is not None and not isinstance(self.source, SourceRef):
            raise TariffError(f"{self.code.value}: source must be a SourceRef or None")


@dataclass(frozen=True, slots=True)
class TodRate:
    """The adjustment per kVAh in one time-of-day zone (negative for a rebate)."""

    zone: TodZone
    hours: str  # display only, e.g. '18:00-22:00'; zone consumption comes from the meter
    rate: Rate

    def __post_init__(self) -> None:
        if not isinstance(self.zone, TodZone):
            raise TariffError("TodRate.zone must be a TodZone")
        _text(self.hours, "TodRate.hours")
        if not isinstance(self.rate, Rate) or self.rate.unit is not Unit.KVAH:
            raise TariffError(f"ToD rate for {self.zone.value} must be a Rate per kVAh")


def _percent(value: DecimalInput, places: int, what: str) -> Decimal:
    number = to_decimal(value, what=what)
    check_places(number, places, what=what)
    if number < 0 or number > 100:
        raise TariffError(f"{what}: {number} is outside 0 to 100")
    return number


@dataclass(frozen=True, slots=True)
class Tariff:
    """One HT industrial tariff, in the shape of SAMAY-DEMO-1 (see docs/tariffs)."""

    tariff_id: str
    name: str
    status: DataStatus
    demand_rate: Rate  # per kVA of billing demand, per billing period
    demand_floor_percent: Decimal  # billing demand is at least this % of contract demand
    excess_demand_multiplier: Decimal  # excess demand pays demand_rate x this
    energy_rate: Rate  # per kVAh
    tod_rates: tuple[TodRate, ...]  # exactly one per TodZone
    duty_percent: Decimal  # of the rounded demand, excess, energy and ToD lines
    line_rounding: RoundingRule  # each money line is rounded once with this
    total_rounding: RoundingRule  # the payable total; the difference is the rounding-off line
    components: tuple[ComponentTerms, ...]  # exactly one per calculated code
    assumptions: tuple[Assumption, ...] = ()  # tariff-wide assumptions

    def __post_init__(self) -> None:
        _text(self.tariff_id, "Tariff.tariff_id")
        _text(self.name, "Tariff.name")
        if not isinstance(self.status, DataStatus):
            raise TariffError("Tariff.status must be a DataStatus")
        self._check_rate(
            self.demand_rate, Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD, "demand"
        )
        self._check_rate(self.energy_rate, Unit.KVAH, RateBasis.PER_UNIT, "energy")
        object.__setattr__(
            self,
            "demand_floor_percent",
            _percent(self.demand_floor_percent, 2, "Tariff.demand_floor_percent"),
        )
        object.__setattr__(
            self, "duty_percent", _percent(self.duty_percent, 6, "Tariff.duty_percent")
        )
        multiplier = to_decimal(self.excess_demand_multiplier, what="excess_demand_multiplier")
        check_places(multiplier, 3, what="excess_demand_multiplier")
        if multiplier < 0 or multiplier > 100:
            raise TariffError(f"excess_demand_multiplier: {multiplier} is outside 0 to 100")
        object.__setattr__(self, "excess_demand_multiplier", multiplier)

        if not isinstance(self.tod_rates, tuple) or not all(
            isinstance(t, TodRate) for t in self.tod_rates
        ):
            raise TariffError("Tariff.tod_rates must be a tuple of TodRate")
        zones = [t.zone for t in self.tod_rates]
        if sorted(z.value for z in zones) != sorted(z.value for z in TodZone):
            raise TariffError("Tariff.tod_rates needs exactly one rate for each ToD zone")

        for name in ("line_rounding", "total_rounding"):
            if not isinstance(getattr(self, name), RoundingRule):
                raise TariffError(f"Tariff.{name} must be a RoundingRule")

        if not isinstance(self.components, tuple) or not all(
            isinstance(c, ComponentTerms) for c in self.components
        ):
            raise TariffError("Tariff.components must be a tuple of ComponentTerms")
        codes = [c.code for c in self.components]
        if len(codes) != len(set(codes)) or set(codes) != set(CALCULATED_CODES):
            raise TariffError("Tariff.components needs exactly one entry per calculated component")
        if not isinstance(self.assumptions, tuple) or not all(
            isinstance(a, Assumption) for a in self.assumptions
        ):
            raise TariffError("Tariff.assumptions must be a tuple of Assumption")

        if self.status is DataStatus.VERIFIED:
            unsourced = [c.code.value for c in self.components if c.source is None]
            if unsourced:
                raise TariffError(
                    f"a VERIFIED tariff needs a source for every component; missing: "
                    f"{', '.join(unsourced)}"
                )

    @staticmethod
    def _check_rate(rate: object, unit: Unit, basis: RateBasis, what: str) -> None:
        if not isinstance(rate, Rate) or rate.unit is not unit or rate.basis is not basis:
            raise TariffError(f"the {what} rate must be a Rate per {unit.value}, {basis.value}")
        if rate.paise_per_unit < 0:
            raise TariffError(f"the {what} rate must not be negative")

    def terms(self, code: ComponentCode) -> ComponentTerms:
        for component in self.components:
            if component.code is code:
                return component
        raise TariffError(f"{self.tariff_id} has no terms for {code.value}")

    def tod_rate(self, zone: TodZone) -> Rate:
        return next(t.rate for t in self.tod_rates if t.zone is zone)

    def source_note(self, code: ComponentCode) -> str:
        """How a tariff parameter is labelled in provenance notes."""
        source = self.terms(code).source
        where = str(source) if source is not None else "no source (synthetic value)"
        return f"tariff {self.tariff_id}, {code.value}: {where}"

    @property
    def is_synthetic(self) -> bool:
        return self.status is DataStatus.SYNTHETIC
