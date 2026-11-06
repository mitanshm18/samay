"""Meter readings tied to a meter and a time interval.

A power factor is only meaningful when active and apparent energy were
measured by the same meter over the same interval, so average_power_factor()
accepts only IntervalReading values and checks that they match.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from .errors import IntervalMismatchError, InvalidValueError, UnitMismatchError
from .units import ApparentEnergy, Energy, PowerFactor, Quantity


@dataclass(frozen=True, slots=True)
class MeterInterval:
    """A half-open interval [start, end) on one meter, with timezone-aware times."""

    meter_id: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.meter_id, str) or not self.meter_id.strip():
            raise InvalidValueError("MeterInterval needs a non-empty meter_id")
        for name, moment in (("start", self.start), ("end", self.end)):
            if not isinstance(moment, datetime):
                raise TypeError(f"MeterInterval.{name} must be a datetime")
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise InvalidValueError(
                    f"MeterInterval.{name} must be timezone-aware (e.g. Asia/Kolkata)"
                )
        if self.end <= self.start:
            raise InvalidValueError("MeterInterval.end must be after start")

    def same_as(self, other: MeterInterval) -> bool:
        """Same meter and the same instants (time zones may differ in notation)."""
        return (
            self.meter_id == other.meter_id and self.start == other.start and self.end == other.end
        )

    def __str__(self) -> str:
        return f"{self.meter_id} [{self.start.isoformat()} .. {self.end.isoformat()})"


@dataclass(frozen=True, slots=True)
class IntervalReading[Q: Quantity]:
    """A quantity measured on one meter over one interval."""

    quantity: Q
    interval: MeterInterval

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, Quantity):
            raise TypeError("IntervalReading.quantity must be a Quantity")
        if not isinstance(self.interval, MeterInterval):
            raise TypeError("IntervalReading.interval must be a MeterInterval")


def average_power_factor(
    active: IntervalReading[Energy], apparent: IntervalReading[ApparentEnergy]
) -> PowerFactor:
    """kWh / kVAh for the same meter and interval, as an exact PowerFactor.

    Raises IntervalMismatchError if the readings come from different meters or
    intervals, and InvalidValueError if the data cannot be consistent (no
    apparent energy, or more active than apparent energy).
    """
    if not isinstance(active.quantity, Energy):
        raise UnitMismatchError(
            f"active reading must be Energy (kWh), got {type(active.quantity).__name__}"
        )
    if not isinstance(apparent.quantity, ApparentEnergy):
        raise UnitMismatchError(
            "apparent reading must be ApparentEnergy (kVAh), "
            f"got {type(apparent.quantity).__name__}"
        )
    if not active.interval.same_as(apparent.interval):
        raise IntervalMismatchError(
            "power factor needs readings from the same meter and interval: "
            f"{active.interval} vs {apparent.interval}"
        )
    kwh = active.quantity.value
    kvah = apparent.quantity.value
    if kvah == 0:
        raise InvalidValueError(
            f"no apparent energy recorded for {apparent.interval}; power factor is undefined"
        )
    if kwh > kvah:
        raise InvalidValueError(
            f"inconsistent readings for {active.interval}: {kwh} kWh exceeds {kvah} kVAh"
        )
    return PowerFactor(Fraction(kwh) / Fraction(kvah))
