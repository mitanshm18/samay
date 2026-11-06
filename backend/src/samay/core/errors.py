"""Errors raised by the calculation core.

Each error also subclasses the closest built-in exception, so callers can catch
either the specific SAMAY error or the general Python one.
"""


class SamayCoreError(Exception):
    """Base class for every error raised by samay.core."""


class InvalidValueError(SamayCoreError, ValueError):
    """A value is outside its allowed range or cannot be parsed."""


class PrecisionError(InvalidValueError):
    """A value carries more precision than allowed and would need rounding.

    The core never rounds silently; the caller must round with an explicit rule.
    """


class UnitMismatchError(SamayCoreError, TypeError):
    """Two quantities with incompatible units were combined."""


class IntervalMismatchError(SamayCoreError, ValueError):
    """Two meter readings do not describe the same meter and interval."""


class ProvenanceError(SamayCoreError, ValueError):
    """A traced value breaks a provenance rule."""


class MissingValueError(SamayCoreError, LookupError):
    """The number of a value marked MISSING was requested."""
