"""Shared bill builders for the billing tests (all values synthetic)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from samay.billing import BillInput, PrintedLine, ZoneConsumption
from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    Energy,
    MeterInterval,
    Money,
    Traced,
)
from samay.tariffs import ComponentCode

IST = timezone(timedelta(hours=5, minutes=30))
SYN = DataStatus.SYNTHETIC
VER = DataStatus.VERIFIED
APRIL = MeterInterval("M1", datetime(2026, 4, 1, tzinfo=IST), datetime(2026, 5, 1, tzinfo=IST))


def entered(value: Any, status: DataStatus = VER) -> Traced[Any]:
    return Traced.entered(value, by="test fixture", status=status)


def zones(peak: str, off_peak: str, normal: str, status: DataStatus = VER) -> ZoneConsumption:
    return ZoneConsumption(
        entered(ApparentEnergy(peak), status),
        entered(ApparentEnergy(off_peak), status),
        entered(ApparentEnergy(normal), status),
    )


def other(label: str, rupees: str) -> PrintedLine:
    return PrintedLine(ComponentCode.OTHER, label, entered(Money.from_rupees(rupees)))


def _q(kind: type[Any], value: str | Traced[Any], status: DataStatus) -> Traced[Any]:
    return value if isinstance(value, Traced) else entered(kind(value), status)


def bill(
    *,
    cd: str | Traced[Any] = "500",
    md: str | Traced[Any] = "412.345",
    kwh: str | Traced[Any] = "90000",
    kvah: str | Traced[Any] = "100000",
    tod: ZoneConsumption | None = None,
    printed: tuple[PrintedLine, ...] = (),
    period: MeterInterval = APRIL,
    status: DataStatus = VER,
    **overrides: Any,
) -> BillInput:
    fields: dict[str, Any] = {
        "bill_id": "TEST-1",
        "period": period,
        "contract_demand": _q(ApparentPower, cd, status),
        "recorded_md": _q(ApparentPower, md, status),
        "kwh": _q(Energy, kwh, status),
        "kvah": _q(ApparentEnergy, kvah, status),
        "zones": tod if tod is not None else zones("25000", "30000", "45000", status),
        "printed_lines": printed,
    }
    fields.update(overrides)
    return BillInput(**fields)
