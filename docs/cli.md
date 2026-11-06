# Command line

```bash
make bill-validate  FILE=examples/bills/matching.json
make bill-calculate FILE=examples/bills/missing-data.json
make bill-reconcile FILE=examples/bills/differing.json FORMAT=json
```

The make targets run `python -m samay.cli <command> <file> [--format text|json] [--debug]`
inside `backend/.venv`. They only read the file and print; nothing is written,
installed or started, and Docker is never used.

| Command | Does | Exit code |
| --- | --- | --- |
| `validate` | checks the file and lists every problem | 0 valid, 2 invalid |
| `calculate` | recalculates the bill with its tariff | 0, or 2 if invalid |
| `reconcile` | recalculates and compares with the printed bill | 0 clean, 1 not clean, 2 invalid |

Exit code 1 from `reconcile` means at least one of: a line differs, a line could not be
compared (absent, illegible or missing), a total difference, or a total that cannot be
determined. Exit code 3 is an internal SAMAY error: one line on stderr (or a JSON
document with `internal_error`), with a traceback only when `--debug` is given.
Usage mistakes (unknown command, missing file argument) exit 2.

## Output

- Text (default): the SYNTHETIC banner first, then the result, then warnings. Missing
  values show as `MISSING (reasons)`; undeterminable differences as
  `not determinable (reasons)`. Input errors go to stderr.
- JSON (`--format json`): stdout holds exactly one `samay.report/1` document, also for
  invalid input and internal errors. See [json-format.md](json-format.md).

## Examples

| File | Shows | `reconcile` exit |
| --- | --- | --- |
| `matching.json` | every line printed and equal | 0 |
| `differing.json` | energy printed 1 paisa high: `DIFFERS` +1, totals equal, residual −1, `COMPLETE` | 1 |
| `pass-through.json` | excess line not printed (`CALCULATED_ONLY`), estimated duty, meter rent (`NOT_RECALCULATED`) | 1 |
| `missing-data.json` | no ToD readings: ToD, duty and rounding off `CANNOT_COMPARE`, total not determinable | 1 |

All examples use SAMAY-DEMO-1, whose rates are made up: no result is a real bill.
