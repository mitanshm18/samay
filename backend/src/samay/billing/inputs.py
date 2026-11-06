"""What SAMAY needs to know about one billing period, with provenance on every value.

Every number is a Traced value, so a reading the user did not have is an
explicit MISSING value with a reason, never a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from samay.core import ApparentEnergy, ApparentPower, Energy, MeterInterval, Money, Traced
from samay.tariffs import ComponentCode, TodZone


def _check_traced(value: object, kind: type[Any], what: str) -> None:
    if not isinstance(value, Traced):
        raise TypeError(f"{what} must be a Traced value (use Traced.missing() if unknown)")
    if value.raw is not None and not isinstance(value.raw, kind):
        raise TypeError(f"{what} must hold {kind.__name__}, got {type(value.raw).__name__}")


def _check_text(value: object, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be non-empty text")


@dataclass(frozen=True, slots=True)
class ZoneConsumption:
    """kVAh in each time-of-day zone. A zone the meter did not report is MISSING."""

    peak: Traced[ApparentEnergy]
    off_peak: Traced[ApparentEnergy]
    normal: Traced[ApparentEnergy]

    def __post_init__(self) -> None:
        for zone in TodZone:
            _check_traced(self.of(zone), ApparentEnergy, f"ZoneConsumption.{zone.value}")

    def of(self, zone: TodZone) -> Traced[ApparentEnergy]:
        value: Traced[ApparentEnergy] = getattr(self, zone.value)
        return value

    def items(self) -> tuple[tuple[TodZone, Traced[ApparentEnergy]], ...]:
        return tuple((zone, self.of(zone)) for zone in TodZone)

    @property
    def is_complete(self) -> bool:
        return not any(value.is_missing for _, value in self.items())


@dataclass(frozen=True, slots=True)
class PrintedLine:
    """One money line as printed on the utility's bill, tagged by the user (D6)."""

    code: ComponentCode
    label: str
    amount: Traced[Money]

    def __post_init__(self) -> None:
        if not isinstance(self.code, ComponentCode):
            raise TypeError("PrintedLine.code must be a ComponentCode")
        _check_text(self.label, "PrintedLine.label")
        _check_traced(self.amount, Money, f"printed line {self.label!r}")


@dataclass(frozen=True, slots=True)
class BillInput:
    """Meter readings and printed lines for one HT connection and billing period."""

    bill_id: str
    period: MeterInterval
    contract_demand: Traced[ApparentPower]
    recorded_md: Traced[ApparentPower]
    kwh: Traced[Energy]
    kvah: Traced[ApparentEnergy]
    zones: ZoneConsumption | None = None
    printed_lines: tuple[PrintedLine, ...] = ()
    printed_total: Traced[Money] | None = None

    def __post_init__(self) -> None:
        _check_text(self.bill_id, "BillInput.bill_id")
        if not isinstance(self.period, MeterInterval):
            raise TypeError("BillInput.period must be a MeterInterval")
        _check_traced(self.contract_demand, ApparentPower, "contract demand")
        _check_traced(self.recorded_md, ApparentPower, "recorded maximum demand")
        _check_traced(self.kwh, Energy, "kWh")
        _check_traced(self.kvah, ApparentEnergy, "kVAh")
        if self.zones is not None and not isinstance(self.zones, ZoneConsumption):
            raise TypeError("BillInput.zones must be a ZoneConsumption or None")
        if not isinstance(self.printed_lines, tuple) or not all(
            isinstance(line, PrintedLine) for line in self.printed_lines
        ):
            raise TypeError("BillInput.printed_lines must be a tuple of PrintedLine")
        if self.printed_total is not None:
            _check_traced(self.printed_total, Money, "printed total")

    @property
    def pass_through_lines(self) -> tuple[PrintedLine, ...]:
        """Printed lines tagged 'other': included as printed, not recalculated (C7)."""
        return tuple(line for line in self.printed_lines if line.code is ComponentCode.OTHER)
