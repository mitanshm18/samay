"""Input errors: every problem found in a bill file, each with a JSON path."""

from __future__ import annotations

from dataclasses import dataclass

from samay.core import SamayCoreError


@dataclass(frozen=True, slots=True)
class InputError:
    """One problem in the input. path is a JSON path such as $.readings.kvah.value."""

    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message} [{self.code}]"


class BillInputError(SamayCoreError, ValueError):
    """The input is invalid; errors lists every problem found (at least one)."""

    def __init__(self, errors: tuple[InputError, ...]) -> None:
        if not errors:
            raise ValueError("BillInputError needs at least one error")
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors))
