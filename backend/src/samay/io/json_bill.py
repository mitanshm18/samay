"""Strict reader for bill files in the samay.bill/1 JSON format (docs/json-format.md).

Rules (decision 0004, D2, D4, D5):

- Every number is a JSON string. Bare JSON numbers, NaN and Infinity are
  refused; they are intercepted by json's parse hooks, so no float is ever made.
- Unknown keys and duplicate keys are errors.
- A traced value is {"value", "provenance", "note"}; a missing value is
  {"provenance": "missing", "note": "why"} with no value. null is refused.
- All independent field errors are collected. Malformed JSON syntax gives one
  syntax error, because recovery is not reliable.
- Only SAMAY's own errors (SamayCoreError) and known parse failures become
  input errors. Anything else is a bug and is left to propagate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from samay.billing import BillInput, PrintedLine, ZoneConsumption, validate_bill
from samay.billing.validation import Severity, ValidationIssue
from samay.core import (
    ApparentEnergy,
    ApparentPower,
    DataStatus,
    Energy,
    MeterInterval,
    Money,
    SamayCoreError,
    Traced,
)
from samay.tariffs import ComponentCode, Tariff, get_tariff

from .errors import BillInputError, InputError

FORMAT = "samay.bill/1"
MAX_BYTES = 1_000_000
_NUMBER = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
_PROVENANCES = ("entered", "extracted", "estimated", "missing")

# Validation issue codes from samay.billing.validation, and where they point.
_ISSUE_PATHS = {
    "contract-demand-zero": "$.readings.contract_demand_kva",
    "kwh-above-kvah": "$.readings.kwh",
    "tod-zones-sum": "$.readings.tod_kvah",
    "tod-zones-exceed": "$.readings.tod_kvah",
    "duplicate-printed-code": "$.printed.lines",
}


class _BareNumber:
    """A JSON number or constant, kept as text so it can be reported, never converted."""

    def __init__(self, text: str) -> None:
        self.text = text


class _Object:
    """A JSON object with its key order and any duplicate keys preserved."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self.pairs = pairs


@dataclass(frozen=True, slots=True)
class LoadedBill:
    bill: BillInput
    tariff: Tariff
    warnings: tuple[ValidationIssue, ...]  # validation warnings (errors raise instead)


class _Reader:
    def __init__(self) -> None:
        self.errors: list[InputError] = []
        self.status = DataStatus.SYNTHETIC  # replaced by data_status once read

    def error(self, path: str, code: str, message: str) -> None:
        self.errors.append(InputError(path, code, message))

    # ---- structure -----------------------------------------------------------

    def obj(
        self, value: Any, path: str, required: tuple[str, ...], optional: tuple[str, ...] = ()
    ) -> dict[str, Any] | None:
        """The object's keys, after checking duplicates, unknown and missing keys."""
        if not isinstance(value, _Object):
            self.wrong_type(value, path, "an object")
            return None
        found: dict[str, Any] = {}
        for key, item in value.pairs:
            if key in found:
                self.error(f"{path}.{key}", "duplicate-key", f"key {key!r} appears more than once")
                continue
            found[key] = item
            if key not in required and key not in optional:
                allowed = ", ".join(required + optional)
                self.error(
                    f"{path}.{key}", "unknown-key", f"unknown key {key!r}; allowed: {allowed}"
                )
        for key in required:
            if key not in found:
                self.error(f"{path}.{key}", "missing-key", f"required key {key!r} is missing")
        return found

    def wrong_type(self, value: Any, path: str, expected: str) -> None:
        if isinstance(value, _BareNumber):
            self.error(
                path,
                "number-not-string",
                f"bare JSON number {value.text} is not accepted; write it as a string, "
                f'e.g. "{value.text}"',
            )
        else:
            self.error(path, "wrong-type", f"expected {expected}, got {_describe(value)}")

    def text(self, value: Any, path: str) -> str | None:
        if not isinstance(value, str):
            self.wrong_type(value, path, "a string")
            return None
        if not value.strip():
            self.error(path, "empty-string", "must not be empty")
            return None
        return value

    def number(self, value: Any, path: str, make: Callable[[str], Any]) -> Any:
        """A decimal string turned into a SAMAY value by make (which checks precision)."""
        text = self.text(value, path)
        if text is None:
            return None
        if not _NUMBER.fullmatch(text):
            self.error(
                path,
                "not-a-decimal",
                f"{text!r} is not a plain decimal number (digits, optional '-' and '.'; "
                "no spaces, '+', exponents or leading zeros)",
            )
            return None
        try:
            return make(text)
        except SamayCoreError as error:
            self.error(path, "invalid-number", str(error))
            return None

    # ---- traced values ---------------------------------------------------------

    def traced(self, value: Any, path: str, make: Callable[[str], Any], kind: type[Any]) -> Any:
        fields = self.obj(value, path, ("provenance", "note"), ("value",))
        if fields is None:
            return None
        provenance = (
            self.text(fields.get("provenance"), f"{path}.provenance")
            if ("provenance" in fields)
            else None
        )
        note = self.text(fields.get("note"), f"{path}.note") if "note" in fields else None
        if provenance is not None and provenance not in _PROVENANCES:
            self.error(
                f"{path}.provenance",
                "invalid-provenance",
                f"{provenance!r} is not one of {', '.join(_PROVENANCES)}"
                + (
                    " (calculated values are made by SAMAY, not entered)"
                    if provenance == "calculated"
                    else ""
                ),
            )
            provenance = None
        raw = None
        if provenance == "missing":
            if "value" in fields:
                self.error(
                    f"{path}.value",
                    "value-with-missing",
                    "a missing value must not have a value; give only provenance and note",
                )
        elif "value" not in fields:
            if provenance is not None:
                self.error(
                    f"{path}.value",
                    "missing-key",
                    'required key "value" is missing (for an unknown value use '
                    '{"provenance": "missing", "note": "why"})',
                )
        else:
            raw = self.number(fields["value"], f"{path}.value", make)
        if provenance is None or note is None:
            return None
        if provenance == "missing":
            return Traced.missing(reason=note, status=self.status, kind=kind)
        if raw is None:
            return None
        if provenance == "entered":
            return Traced.entered(raw, by=note, status=self.status)
        if provenance == "extracted":
            return Traced.extracted(raw, source=note, status=self.status)
        return Traced.estimated(raw, basis=note, status=self.status)

    # ---- sections ----------------------------------------------------------------

    def period(self, value: Any) -> MeterInterval | None:
        fields = self.obj(value, "$.period", ("meter_id", "start", "end"))
        if fields is None:
            return None
        meter = (
            self.text(fields.get("meter_id"), "$.period.meter_id")
            if ("meter_id" in fields)
            else None
        )
        start = self.moment(fields["start"], "$.period.start") if "start" in fields else None
        end = self.moment(fields["end"], "$.period.end") if "end" in fields else None
        if meter is None or start is None or end is None:
            return None
        try:
            return MeterInterval(meter, start, end)
        except SamayCoreError as error:
            self.error("$.period", "invalid-period", str(error))
            return None

    def moment(self, value: Any, path: str) -> datetime | None:
        text = self.text(value, path)
        if text is None:
            return None
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            self.error(path, "invalid-time", f"{text!r} is not an ISO 8601 date and time")
            return None
        if moment.tzinfo is None:
            self.error(path, "time-without-offset", f"{text!r} needs a UTC offset, e.g. +05:30")
            return None
        return moment

    def printed_line(self, value: Any, path: str) -> PrintedLine | None:
        fields = self.obj(value, path, ("code", "label", "amount_rupees"))
        if fields is None:
            return None
        code = None
        if "code" in fields:
            text = self.text(fields["code"], f"{path}.code")
            if text is not None:
                known = {c.value: c for c in ComponentCode}
                code = known.get(text)
                if code is None:
                    self.error(
                        f"{path}.code",
                        "unknown-line-code",
                        f"unknown line code {text!r}; accepted: {', '.join(known)}. "
                        "Tag any line SAMAY does not recalculate as 'other'.",
                    )
        label = self.text(fields["label"], f"{path}.label") if "label" in fields else None
        amount = (
            self.traced(fields["amount_rupees"], f"{path}.amount_rupees", Money.from_rupees, Money)
            if "amount_rupees" in fields
            else None
        )
        if code is None or label is None or amount is None:
            return None
        return PrintedLine(code, label, amount)


def _describe(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, _Object):
        return "an object"
    if isinstance(value, list):
        return "a list"
    return type(value).__name__


def _decode(data: bytes) -> tuple[Any, InputError | None]:
    if len(data) > MAX_BYTES:
        return None, InputError("$", "too-large", f"the file is over {MAX_BYTES} bytes")
    if data.startswith(b"\xef\xbb\xbf"):
        return None, InputError("$", "byte-order-mark", "the file starts with a byte order mark")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, InputError("$", "not-utf8", f"the file is not valid UTF-8 ({error.reason})")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_Object,
            parse_int=_BareNumber,
            parse_float=_BareNumber,
            parse_constant=_BareNumber,
        )
    except json.JSONDecodeError as error:
        return None, InputError(
            "$",
            "json-syntax",
            f"malformed JSON at line {error.lineno}, column {error.colno}: {error.msg}",
        )
    except RecursionError:
        return None, InputError("$", "too-deep", "the JSON is nested too deeply")
    return parsed, None


def load_bill(data: bytes) -> LoadedBill:
    """Parse and validate a bill file; raise BillInputError listing every problem."""
    if not isinstance(data, bytes):
        raise TypeError("load_bill() takes the file's bytes")
    parsed, syntax = _decode(data)
    if syntax is not None:
        raise BillInputError((syntax,))
    reader = _Reader()
    top = reader.obj(
        parsed,
        "$",
        ("format", "bill_id", "tariff_id", "data_status", "period", "readings"),
        ("printed",),
    )
    if top is None:
        raise BillInputError(tuple(reader.errors))

    if "format" in top:
        fmt = reader.text(top["format"], "$.format")
        if fmt is not None and fmt != FORMAT:
            reader.error("$.format", "unknown-format", f"expected {FORMAT!r}, got {fmt!r}")
    if "data_status" in top:
        status = reader.text(top["data_status"], "$.data_status")
        if status is not None:
            try:
                reader.status = DataStatus(status)
            except ValueError:
                reader.error(
                    "$.data_status",
                    "invalid-data-status",
                    f"{status!r} is not 'synthetic' or 'verified'",
                )
    bill_id = reader.text(top["bill_id"], "$.bill_id") if "bill_id" in top else None
    tariff = None
    if "tariff_id" in top:
        tariff_id = reader.text(top["tariff_id"], "$.tariff_id")
        if tariff_id is not None:
            try:
                tariff = get_tariff(tariff_id)
            except SamayCoreError as error:
                reader.error("$.tariff_id", "unknown-tariff", str(error))
    period = reader.period(top["period"]) if "period" in top else None

    readings: dict[str, Any] = {}
    zones: ZoneConsumption | None = None
    zones_ok = True
    if "readings" in top:
        fields = reader.obj(
            top["readings"],
            "$.readings",
            ("contract_demand_kva", "recorded_md_kva", "kwh", "kvah"),
            ("tod_kvah",),
        )
        if fields is not None:
            for key, make in (
                ("contract_demand_kva", ApparentPower),
                ("recorded_md_kva", ApparentPower),
                ("kwh", Energy),
                ("kvah", ApparentEnergy),
            ):
                if key in fields:
                    readings[key] = reader.traced(fields[key], f"$.readings.{key}", make, make)
            if "tod_kvah" in fields:
                tod = reader.obj(
                    fields["tod_kvah"], "$.readings.tod_kvah", ("peak", "off_peak", "normal")
                )
                values = {}
                if tod is not None:
                    for zone in ("peak", "off_peak", "normal"):
                        if zone in tod:
                            values[zone] = reader.traced(
                                tod[zone],
                                f"$.readings.tod_kvah.{zone}",
                                ApparentEnergy,
                                ApparentEnergy,
                            )
                if len(values) == 3 and all(v is not None for v in values.values()):
                    zones = ZoneConsumption(values["peak"], values["off_peak"], values["normal"])
                else:
                    zones_ok = False

    lines: list[PrintedLine] = []
    lines_ok = True
    printed_total = None
    total_ok = True
    if "printed" in top:
        printed = reader.obj(top["printed"], "$.printed", (), ("lines", "total_rupees"))
        if printed is not None:
            if "lines" in printed:
                items = printed["lines"]
                if not isinstance(items, list):
                    reader.wrong_type(items, "$.printed.lines", "a list")
                    lines_ok = False
                else:
                    for index, item in enumerate(items):
                        line = reader.printed_line(item, f"$.printed.lines[{index}]")
                        if line is None:
                            lines_ok = False
                        else:
                            lines.append(line)
            if "total_rupees" in printed:
                printed_total = reader.traced(
                    printed["total_rupees"], "$.printed.total_rupees", Money.from_rupees, Money
                )
                total_ok = printed_total is not None

    if (
        reader.errors
        or bill_id is None
        or period is None
        or tariff is None
        or len(readings) != 4
        or any(v is None for v in readings.values())
        or not (zones_ok and lines_ok and total_ok)
    ):
        # Every path that leaves a field unset records an error first, so the
        # list is never empty here; if it were, BillInputError() raises (a bug).
        raise BillInputError(tuple(reader.errors))
    bill = BillInput(
        bill_id=bill_id,
        period=period,
        contract_demand=readings["contract_demand_kva"],
        recorded_md=readings["recorded_md_kva"],
        kwh=readings["kwh"],
        kvah=readings["kvah"],
        zones=zones,
        printed_lines=tuple(lines),
        printed_total=printed_total,
    )
    issues = validate_bill(bill, tariff)
    errors = [
        InputError(_ISSUE_PATHS.get(issue.code, "$"), issue.code, issue.message)
        for issue in issues
        if issue.severity is Severity.ERROR
    ]
    if errors:
        raise BillInputError(tuple(errors))
    warnings = tuple(issue for issue in issues if issue.severity is Severity.WARNING)
    return LoadedBill(bill, tariff, warnings)
