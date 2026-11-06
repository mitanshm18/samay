"""Strict samay.bill/1 reader: every rule, every error code, all errors collected."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from samay.core import ApparentPower, DataStatus, Money, Provenance
from samay.io import BillInputError, InputError, load_bill
from samay.io.json_bill import MAX_BYTES
from samay.tariffs import ComponentCode

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bills"


def example(name: str = "matching") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text("utf-8"))
    return data


def encode(data: Any) -> bytes:
    return json.dumps(data).encode("utf-8")


def errors(data: Any) -> list[InputError]:
    raw = data if isinstance(data, bytes) else encode(data)
    with pytest.raises(BillInputError) as caught:
        load_bill(raw)
    return list(caught.value.errors)


def codes(data: Any) -> list[tuple[str, str]]:
    return [(e.path, e.code) for e in errors(data)]


# ---- valid files --------------------------------------------------------------------


@pytest.mark.parametrize("name", ["matching", "differing", "pass-through", "missing-data"])
def test_examples_load(name: str) -> None:
    loaded = load_bill((EXAMPLES / f"{name}.json").read_bytes())
    assert loaded.tariff.tariff_id == "SAMAY-DEMO-1"
    assert loaded.bill.bill_id.startswith("EXAMPLE-")


def test_values_and_provenance_are_kept() -> None:
    loaded = load_bill(encode(example()))
    bill = loaded.bill
    assert bill.recorded_md.value == ApparentPower("412.345")
    assert bill.recorded_md.provenance is Provenance.EXTRACTED
    assert bill.recorded_md.note == "example bill p.1, recorded MD"
    assert bill.contract_demand.provenance is Provenance.ENTERED
    assert bill.contract_demand.status is DataStatus.SYNTHETIC
    assert bill.printed_lines[0].code is ComponentCode.DEMAND_CHARGE
    assert bill.printed_lines[0].amount.value == Money(16_493_800)
    assert bill.printed_total is not None
    assert bill.printed_total.value == Money(112_606_000)
    assert [w.code for w in loaded.warnings] == ["synthetic-tariff"]


def test_missing_and_estimated_values() -> None:
    data = example()
    data["readings"]["kwh"] = {"provenance": "missing", "note": "kWh not printed"}
    data["readings"]["kvah"]["provenance"] = "estimated"
    data["printed"]["lines"][0]["amount_rupees"] = {"provenance": "missing", "note": "smudged"}
    bill = load_bill(encode(data)).bill
    assert bill.kwh.is_missing
    assert bill.kwh.note == "kWh not printed"
    assert bill.kvah.provenance is Provenance.ESTIMATED
    assert bill.printed_lines[0].amount.is_missing


def test_optional_sections() -> None:
    data = example()
    del data["printed"]
    del data["readings"]["tod_kvah"]
    bill = load_bill(encode(data)).bill
    assert bill.printed_lines == ()
    assert bill.printed_total is None
    assert bill.zones is None
    data = example()
    data["printed"] = {}
    assert load_bill(encode(data)).bill.printed_lines == ()


def test_verified_data_status() -> None:
    data = example()
    data["data_status"] = "verified"
    bill = load_bill(encode(data)).bill
    assert bill.kvah.status is DataStatus.VERIFIED


# ---- numbers must be strings ----------------------------------------------------------


@pytest.mark.parametrize("raw", ["412.345", "412", "4.12e2", "NaN", "Infinity", "-Infinity"])
def test_bare_numbers_are_refused(raw: str) -> None:
    text = json.dumps(example()).replace('"412.345"', raw)
    assert codes(text.encode()) == [("$.readings.recorded_md_kva.value", "number-not-string")]


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("4.12e2", "not-a-decimal"),
        (" 412.345", "not-a-decimal"),
        ("+412.345", "not-a-decimal"),
        ("0412.345", "not-a-decimal"),
        ("412,345", "not-a-decimal"),
        ("412.3456", "invalid-number"),  # more than 3 places: refused, never rounded
        ("-1", "invalid-number"),  # demand cannot be negative
        ("", "empty-string"),
    ],
)
def test_decimal_strings_are_strict(value: str, code: str) -> None:
    data = example()
    data["readings"]["recorded_md_kva"]["value"] = value
    assert codes(data) == [("$.readings.recorded_md_kva.value", code)]


def test_money_precision() -> None:
    data = example()
    data["printed"]["lines"][0]["amount_rupees"]["value"] = "164938.005"
    found = errors(data)
    assert [(e.path, e.code) for e in found] == [
        ("$.printed.lines[0].amount_rupees.value", "invalid-number")
    ]
    assert "decimal places" in found[0].message
    data["printed"]["lines"][0]["amount_rupees"]["value"] = "-12.50"  # credits are allowed
    assert load_bill(encode(data)).bill.printed_lines[0].amount.value == Money(-1250)


@pytest.mark.parametrize("value", [None, True, ["1"], {"v": "1"}])
def test_wrong_types(value: object) -> None:
    data = example()
    data["readings"]["kvah"]["value"] = value
    assert codes(data) == [("$.readings.kvah.value", "wrong-type")]


# ---- structure ----------------------------------------------------------------------


def test_unknown_and_missing_keys() -> None:
    data = example()
    data["extra"] = "x"
    data["readings"]["kvah"]["unit"] = "kVAh"
    del data["readings"]["kwh"]
    assert sorted(codes(data)) == [
        ("$.extra", "unknown-key"),
        ("$.readings.kvah.unit", "unknown-key"),
        ("$.readings.kwh", "missing-key"),
    ]


def test_duplicate_keys() -> None:
    text = json.dumps(example()).replace(
        '"bill_id": "EXAMPLE-MATCHING"', '"bill_id": "A", "bill_id": "B"'
    )
    assert codes(text.encode()) == [("$.bill_id", "duplicate-key")]


def test_traced_value_rules() -> None:
    data = example()
    data["readings"]["kwh"] = {"value": "1", "provenance": "missing", "note": "x"}
    data["readings"]["kvah"] = {"provenance": "extracted", "note": "x"}
    data["readings"]["contract_demand_kva"]["provenance"] = "calculated"
    data["readings"]["recorded_md_kva"]["note"] = " "
    found = errors(data)
    assert sorted((e.path, e.code) for e in found) == [
        ("$.readings.contract_demand_kva.provenance", "invalid-provenance"),
        ("$.readings.kvah.value", "missing-key"),
        ("$.readings.kwh.value", "value-with-missing"),
        ("$.readings.recorded_md_kva.note", "empty-string"),
    ]
    assert any("made by SAMAY" in e.message for e in found)


def test_top_level_must_be_object() -> None:
    assert codes([1]) == [("$", "wrong-type")]
    assert codes(b"7") == [("$", "number-not-string")]


def test_sections_must_be_objects() -> None:
    data = example()
    data["readings"]["tod_kvah"] = ["1", "2", "3"]
    data["printed"]["lines"] = {"a": "b"}
    data["period"] = "April"
    assert sorted(codes(data)) == [
        ("$.period", "wrong-type"),
        ("$.printed.lines", "wrong-type"),
        ("$.readings.tod_kvah", "wrong-type"),
    ]


def test_format_status_and_tariff() -> None:
    data = example()
    data["format"] = "samay.bill/2"
    data["data_status"] = "Synthetic"
    data["tariff_id"] = "UPPCL-HV2"
    assert sorted(codes(data)) == [
        ("$.data_status", "invalid-data-status"),
        ("$.format", "unknown-format"),
        ("$.tariff_id", "unknown-tariff"),
    ]


def test_times() -> None:
    data = example()
    data["period"]["start"] = "2026-04-01T00:00:00"
    data["period"]["end"] = "1st May"
    assert sorted(codes(data)) == [
        ("$.period.end", "invalid-time"),
        ("$.period.start", "time-without-offset"),
    ]
    data = example()
    data["period"]["end"] = data["period"]["start"]
    assert codes(data) == [("$.period", "invalid-period")]


def test_unknown_line_codes_are_reported_never_dropped() -> None:
    data = example()
    lines = data["printed"]["lines"]
    lines[0]["code"] = "fixed_charge"
    lines[1]["code"] = "Energy_Charge"
    lines[2]["code"] = ""
    lines[3]["code"] = 4
    found = errors(json.dumps(data).replace('"code": "4"', '"code": 4').encode())
    assert [(e.path, e.code) for e in found] == [
        ("$.printed.lines[0].code", "unknown-line-code"),
        ("$.printed.lines[1].code", "unknown-line-code"),
        ("$.printed.lines[2].code", "empty-string"),
        ("$.printed.lines[3].code", "number-not-string"),
    ]
    assert "'fixed_charge'" in found[0].message
    assert "other" in found[0].message


def test_all_independent_errors_are_collected() -> None:
    data = example()
    data["bill_id"] = ""
    data["format"] = "x"
    data["readings"]["kwh"]["value"] = "1.0001"
    data["readings"]["tod_kvah"]["peak"]["provenance"] = "guessed"
    data["printed"]["lines"][0]["label"] = ""
    data["printed"]["total_rupees"]["value"] = "1.001"
    data["period"]["meter_id"] = 5
    assert len(errors(json.dumps(data).replace('"meter_id": "5"', '"meter_id": 5').encode())) == 7


def test_validation_errors_come_through_with_paths() -> None:
    data = example()
    data["readings"]["kwh"]["value"] = "100000.001"  # more than kVAh
    data["readings"]["tod_kvah"]["peak"]["value"] = "25000.001"  # zones no longer add up
    assert sorted(codes(data)) == [
        ("$.readings.kwh", "kwh-above-kvah"),
        ("$.readings.tod_kvah", "tod-zones-sum"),
    ]
    data = example()
    data["printed"]["lines"].append(copy.deepcopy(data["printed"]["lines"][0]))
    assert codes(data) == [("$.printed.lines", "duplicate-printed-code")]


# ---- encoding and syntax ------------------------------------------------------------


def test_syntax_error_is_one_error() -> None:
    found = errors(b'{"format": "samay.bill/1",, }')
    assert [(e.path, e.code) for e in found] == [("$", "json-syntax")]
    assert "line 1" in found[0].message


def test_encoding_and_size() -> None:
    assert codes(b"\xef\xbb\xbf{}") == [("$", "byte-order-mark")]
    assert codes(b"\xff\xfe") == [("$", "not-utf8")]
    assert codes(b" " * (MAX_BYTES + 1)) == [("$", "too-large")]
    assert codes(b"[" * 100_000 + b"]" * 100_000) == [("$", "too-deep")]


def test_load_bill_needs_bytes() -> None:
    with pytest.raises(TypeError):
        load_bill("{}")  # type: ignore[arg-type]


def test_input_error_text() -> None:
    error = InputError("$.x", "code", "message")
    assert str(error) == "$.x: message [code]"
    with pytest.raises(ValueError, match="at least one"):
        BillInputError(())


@given(st.binary(max_size=200))
def test_random_bytes_never_escape_as_raw_errors(data: bytes) -> None:
    with pytest.raises(BillInputError):
        load_bill(data)


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=5),
    lambda inner: (
        st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=5), inner, max_size=3)
    ),
    max_leaves=10,
)


@given(json_values)
def test_random_json_never_escapes_as_raw_errors(value: object) -> None:
    with pytest.raises(BillInputError):
        load_bill(encode(value))


@given(st.sampled_from(["contract_demand_kva", "recorded_md_kva", "kwh", "kvah"]), json_values)
def test_random_values_in_a_valid_file(key: str, value: object) -> None:
    data = example()
    data["readings"][key]["value"] = value
    found: tuple[InputError, ...] = ()
    try:
        load_bill(encode(data))
    except BillInputError as error:
        found = error.errors
    assert all(e.path.startswith("$.readings") for e in found)


def test_malformed_structures_are_reported_at_their_paths() -> None:
    data = example()
    data["data_status"] = 5
    data["tariff_id"] = ["SAMAY-DEMO-1"]
    data["period"]["start"] = 5
    data["readings"]["kwh"] = "41250"
    data["readings"]["kvah"] = {"provenance": "guessed", "note": "x"}
    del data["readings"]["tod_kvah"]["normal"]
    del data["printed"]["lines"][0]["code"]
    del data["printed"]["lines"][1]["label"]
    assert sorted(codes(data)) == [
        ("$.data_status", "number-not-string"),
        ("$.period.start", "number-not-string"),
        ("$.printed.lines[0].code", "missing-key"),
        ("$.printed.lines[1].label", "missing-key"),
        ("$.readings.kvah.provenance", "invalid-provenance"),
        ("$.readings.kwh", "wrong-type"),
        ("$.readings.tod_kvah.normal", "missing-key"),
        ("$.tariff_id", "wrong-type"),
    ]


def test_sections_that_are_not_objects() -> None:
    data = example()
    data["readings"] = "none"
    data["printed"] = ["lines"]
    assert sorted(codes(data)) == [("$.printed", "wrong-type"), ("$.readings", "wrong-type")]


def test_printed_line_that_is_not_an_object() -> None:
    data = example()
    data["printed"]["lines"][2] = "Energy 900000.00"
    assert codes(data) == [("$.printed.lines[2]", "wrong-type")]
