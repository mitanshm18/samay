"""SAMAY calculation core: pure, deterministic, standard library only.

No database, network, file or clock access happens in this package.
"""

from .errors import (
    IntervalMismatchError,
    InvalidValueError,
    MissingValueError,
    PrecisionError,
    ProvenanceError,
    SamayCoreError,
    UnitMismatchError,
)
from .measurement import IntervalReading, MeterInterval, average_power_factor
from .money import ExactAmount, Money, Rate, RateBasis, format_rupees
from .provenance import DataStatus, Provenance, Traced, combine_status
from .rounding import QuantityRounding, RoundingRule, round_paise
from .units import (
    ApparentEnergy,
    ApparentPower,
    Duration,
    Energy,
    ExactApparentPower,
    Power,
    PowerFactor,
    Quantity,
    ReactiveEnergy,
    Unit,
)

__all__ = [
    "ApparentEnergy",
    "ApparentPower",
    "DataStatus",
    "Duration",
    "Energy",
    "ExactAmount",
    "ExactApparentPower",
    "IntervalMismatchError",
    "IntervalReading",
    "InvalidValueError",
    "MeterInterval",
    "MissingValueError",
    "Money",
    "Power",
    "PowerFactor",
    "PrecisionError",
    "Provenance",
    "ProvenanceError",
    "Quantity",
    "QuantityRounding",
    "Rate",
    "RateBasis",
    "ReactiveEnergy",
    "RoundingRule",
    "SamayCoreError",
    "Traced",
    "Unit",
    "UnitMismatchError",
    "average_power_factor",
    "combine_status",
    "format_rupees",
    "round_paise",
]
