# Bill and report JSON formats

SAMAY reads bills in `samay.bill/1` and writes reports in `samay.report/1`. Both are
strict: nothing is guessed, rounded or defaulted.

## Input: `samay.bill/1`

```json
{
  "format": "samay.bill/1",
  "bill_id": "EXAMPLE-MATCHING",
  "tariff_id": "SAMAY-DEMO-1",
  "data_status": "synthetic",
  "period": {
    "meter_id": "M-EX1",
    "start": "2026-04-01T00:00:00+05:30",
    "end": "2026-05-01T00:00:00+05:30"
  },
  "readings": {
    "contract_demand_kva": {"value": "500.000", "provenance": "entered", "note": "sanctioned load letter"},
    "recorded_md_kva": {"value": "412.345", "provenance": "extracted", "note": "bill p.1, recorded MD"},
    "kwh": {"value": "90000.000", "provenance": "extracted", "note": "bill p.1, kWh"},
    "kvah": {"value": "100000.000", "provenance": "extracted", "note": "bill p.1, kVAh"},
    "tod_kvah": {
      "peak": {"value": "25000.000", "provenance": "extracted", "note": "bill p.2"},
      "off_peak": {"provenance": "missing", "note": "not printed"},
      "normal": {"value": "45000.000", "provenance": "extracted", "note": "bill p.2"}
    }
  },
  "printed": {
    "lines": [
      {"code": "demand_charge", "label": "Demand charge",
       "amount_rupees": {"value": "164938.00", "provenance": "extracted", "note": "line 1"}},
      {"code": "other", "label": "Meter rent",
       "amount_rupees": {"value": "250.00", "provenance": "extracted", "note": "line 7"}}
    ],
    "total_rupees": {"value": "1126060.00", "provenance": "extracted", "note": "amount payable"}
  }
}
```

Complete examples: [`examples/bills/`](../examples/bills/).

| Key | Required | Rule |
| --- | --- | --- |
| `format` | yes | exactly `samay.bill/1` |
| `bill_id`, `tariff_id` | yes | non-empty strings; the tariff must exist (only `SAMAY-DEMO-1` today) |
| `data_status` | yes | `synthetic` or `verified`, for every value in the file |
| `period` | yes | `meter_id`, `start`, `end`; ISO 8601 times with a UTC offset; end after start |
| `readings` | yes | `contract_demand_kva`, `recorded_md_kva`, `kwh`, `kvah`; optional `tod_kvah` with `peak`, `off_peak`, `normal` |
| `printed` | no | optional `lines` (list) and `total_rupees` |

**Traced values.** Every reading and amount is an object:
`{"value": "...", "provenance": "entered" | "extracted" | "estimated", "note": "..."}`, or
`{"provenance": "missing", "note": "why"}` with no `value`. `calculated` is refused
(only SAMAY calculates). The note is required and never blank.

**Numbers are strings.** Plain decimals only: no exponent, no `+`, no leading zeros,
no spaces or commas. Quantities have at most 3 decimal places and are never negative;
rupee amounts have at most 2 places and may be negative (credits). Too many places is
an error, never rounded. A bare JSON number (`412.345`, `NaN`, `1e3`) is refused.

**Printed line codes.** `demand_charge`, `excess_demand_charge`, `energy_charge`,
`tod_adjustment`, `electricity_duty`, `rounding_off`, and `other` for anything SAMAY does
not recalculate (meter rent, arrears). Codes are case-sensitive; an unknown code is an
error. Each code except `other` may appear once.

**Also refused:** unknown keys, duplicate keys, missing required keys, `null`, a byte
order mark, non-UTF-8 bytes, files over 1,000,000 bytes, and nesting too deep to parse.

### Error codes

Each error has a JSON path (for example `$.readings.kwh.value`), a code and a message.
All are reported together; malformed JSON syntax is a single `json-syntax` error.

| Code | Meaning |
| --- | --- |
| `too-large`, `byte-order-mark`, `not-utf8`, `json-syntax`, `too-deep` | the file cannot be read as JSON |
| `cannot-read-file` | the file does not exist or cannot be opened (command line) |
| `duplicate-key`, `unknown-key`, `missing-key` | object keys |
| `wrong-type`, `empty-string`, `number-not-string` | value types |
| `not-a-decimal`, `invalid-number` | decimal format, or a value out of range or too precise |
| `invalid-provenance`, `value-with-missing` | traced values |
| `invalid-time`, `time-without-offset`, `invalid-period` | the billing period |
| `unknown-format`, `invalid-data-status`, `unknown-tariff`, `unknown-line-code` | identifiers |
| `kwh-above-kvah`, `tod-zones-sum`, `tod-zones-exceed`, `contract-demand-zero`, `duplicate-printed-code` | bill validation (decision 0003) |

Warnings (`synthetic-tariff`, `input-estimated`, `tod-zones-missing`, ...) do not stop
the bill; they appear in every report.

## Output: `samay.report/1`

One JSON document per run. Top level: `format`, `command`, `exit_code`, then (when a
tariff is known) `tariff` {`id`, `name`, `status`}, `synthetic`, `banner`, then
`warnings`, `errors`, and `calculation` / `reconciliation` as the command produces them.
`validate` adds `valid`; an internal error gives `internal_error` instead.

Every amount or measurement is written as:

```json
{
  "value": "0.01", "unit": "INR", "paise": "1",
  "provenance": "calculated", "status": "synthetic",
  "note": "difference: printed − calculated",
  "rests_on_estimate": false, "estimate_bases": [],
  "leaves": [ {"provenance": "extracted", "status": "synthetic", "note": "...", "value": "900000.01", "unit": "INR", "paise": "90000001"} ]
}
```

- No JSON numbers: values, paise, counts and `exit_code` are strings.
- `null` appears only as the `value` of a MISSING or undeterminable item (with
  `missing_reasons`), and for the fixed keys `banner`, `rounding` and `exact` when they
  do not apply.
- `reconciliation` holds `lines` (status, printed, calculated, difference), `total`
  (`printed_total_given`, `printed`, `calculated`, `difference`,
  `printed_lines_residual`), `explanation` (`state`, compared count and difference,
  `not_compared` with reasons), `counts`, `taken_as_printed_total`, `clean` and
  `rests_on_estimate`.
