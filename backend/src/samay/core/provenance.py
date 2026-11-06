"""Where every value came from, and whether it rests on synthetic data.

Two separate labels travel with each value:

- Provenance: how the value was obtained (entered, extracted, calculated,
  estimated or missing).
- DataStatus: whether it depends on any synthetic data (SYNTHETIC) or only on
  checked sources (VERIFIED).

Rules enforced here:

1. A value derived from others is CALCULATED and keeps links to its inputs.
2. If any input is SYNTHETIC, the result is SYNTHETIC. Nothing can make a
   synthetic value verified.
3. If any input is MISSING, the result is MISSING, with the reason.
4. Every value carries a non-empty note: who entered it, the source it was
   extracted from, the basis of an estimate, or why it is missing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .errors import MissingValueError, ProvenanceError


class Provenance(Enum):
    ENTERED = "entered"
    EXTRACTED = "extracted"
    CALCULATED = "calculated"
    ESTIMATED = "estimated"
    MISSING = "missing"


class DataStatus(Enum):
    SYNTHETIC = "synthetic"
    VERIFIED = "verified"


def combine_status(statuses: Iterable[DataStatus]) -> DataStatus:
    """SYNTHETIC if any status is SYNTHETIC, otherwise VERIFIED."""
    seen = list(statuses)
    if not seen:
        raise ProvenanceError("combine_status() needs at least one status")
    return DataStatus.SYNTHETIC if DataStatus.SYNTHETIC in seen else DataStatus.VERIFIED


@dataclass(frozen=True, slots=True)
class Traced[T]:
    """A value together with its provenance, data status, note and inputs.

    Create values with the named constructors (entered, extracted, estimated,
    missing) and derive new ones with Traced.derive(); the checks in
    __post_init__ make inconsistent combinations impossible to construct.
    """

    raw: T | None
    provenance: Provenance
    status: DataStatus
    note: str
    inputs: tuple[Traced[Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance")
        if not isinstance(self.status, DataStatus):
            raise TypeError("status must be a DataStatus")
        if not isinstance(self.note, str) or not self.note.strip():
            raise ProvenanceError(f"a {self.provenance.value} value needs a non-empty note")
        if isinstance(self.raw, float):
            raise TypeError("binary floats are not accepted as traced values")
        if not isinstance(self.inputs, tuple) or not all(
            isinstance(i, Traced) for i in self.inputs
        ):
            raise TypeError("inputs must be a tuple of Traced values")

        missing = self.provenance is Provenance.MISSING
        if missing != (self.raw is None):
            raise ProvenanceError("a value is MISSING exactly when it holds no value")
        if self.provenance is Provenance.CALCULATED and not self.inputs:
            raise ProvenanceError("a CALCULATED value must link to its inputs")
        if self.inputs and self.provenance not in (Provenance.CALCULATED, Provenance.MISSING):
            raise ProvenanceError(f"a {self.provenance.value} value cannot have inputs")
        if self.inputs:
            expected = combine_status(i.status for i in self.inputs)
            if self.status is not expected:
                raise ProvenanceError(
                    f"status must be {expected.value}: it is derived from its inputs"
                )
            if not missing and any(i.provenance is Provenance.MISSING for i in self.inputs):
                raise ProvenanceError("a value derived from a MISSING input must be MISSING")

    # ---- leaf constructors -------------------------------------------------

    @classmethod
    def entered(cls, value: T, *, by: str, status: DataStatus) -> Traced[T]:
        """Typed in by a person; by says who or where (e.g. 'plant manager, form B')."""
        return cls(value, Provenance.ENTERED, status, by)

    @classmethod
    def extracted(cls, value: T, *, source: str, status: DataStatus) -> Traced[T]:
        """Read from a document; source names it and the location (page, line)."""
        return cls(value, Provenance.EXTRACTED, status, source)

    @classmethod
    def estimated(cls, value: T, *, basis: str, status: DataStatus) -> Traced[T]:
        """An explicit assumption; basis explains it and is required."""
        return cls(value, Provenance.ESTIMATED, status, basis)

    @staticmethod
    def missing(*, reason: str, status: DataStatus) -> Traced[Any]:
        """No value is available; reason says why."""
        return Traced(None, Provenance.MISSING, status, reason)

    # ---- derivation --------------------------------------------------------

    @staticmethod
    def derive[R](function: Callable[..., R], *inputs: Traced[Any], description: str) -> Traced[R]:
        """Apply function to the inputs' values, recording provenance.

        If any input is MISSING, function is not called and the result is
        MISSING. The result is SYNTHETIC if any input is SYNTHETIC.
        """
        if not inputs:
            raise ProvenanceError("derive() needs at least one input")
        status = combine_status(i.status for i in inputs)
        for item in inputs:
            if item.provenance is Provenance.MISSING:
                return Traced(
                    None,
                    Provenance.MISSING,
                    status,
                    f"{description}: missing input ({item.note})",
                    tuple(inputs),
                )
        result = function(*(item.raw for item in inputs))
        return Traced(result, Provenance.CALCULATED, status, description, tuple(inputs))

    # ---- reading -----------------------------------------------------------

    @property
    def value(self) -> T:
        """The value; raises MissingValueError if it is MISSING (never returns 0)."""
        if self.raw is None:
            raise MissingValueError(self.note)
        return self.raw

    @property
    def is_missing(self) -> bool:
        return self.provenance is Provenance.MISSING

    @property
    def is_synthetic(self) -> bool:
        return self.status is DataStatus.SYNTHETIC

    def leaves(self) -> tuple[Traced[Any], ...]:
        """The original (non-derived) values this one rests on, in first-seen order."""
        seen: dict[int, Traced[Any]] = {}

        def walk(node: Traced[Any]) -> Iterator[Traced[Any]]:
            if not node.inputs:
                yield node
            for child in node.inputs:
                yield from walk(child)

        for leaf in walk(self):
            seen.setdefault(id(leaf), leaf)
        return tuple(seen.values())
