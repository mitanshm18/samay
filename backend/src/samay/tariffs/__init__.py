"""Tariff definitions. Only the synthetic SAMAY-DEMO-1 exists so far."""

from .model import (
    CALCULATED_CODES,
    Assumption,
    ComponentCode,
    ComponentTerms,
    SourceRef,
    Tariff,
    TariffError,
    TodRate,
    TodZone,
)
from .samay_demo_1 import SAMAY_DEMO_1

_REGISTRY: dict[str, Tariff] = {SAMAY_DEMO_1.tariff_id: SAMAY_DEMO_1}


def get_tariff(tariff_id: str) -> Tariff:
    """The tariff with this id; raises TariffError for an unknown id."""
    try:
        return _REGISTRY[tariff_id]
    except (KeyError, TypeError):
        raise TariffError(
            f"unknown tariff {tariff_id!r}; known: {', '.join(sorted(_REGISTRY))}"
        ) from None


__all__ = [
    "CALCULATED_CODES",
    "SAMAY_DEMO_1",
    "Assumption",
    "ComponentCode",
    "ComponentTerms",
    "SourceRef",
    "Tariff",
    "TariffError",
    "TodRate",
    "TodZone",
    "get_tariff",
]
