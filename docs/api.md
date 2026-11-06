# API

SAMAY's HTTP API (Step 5, [decision 0006](decisions/0006-minimal-api.md)). Local only:
it listens on 127.0.0.1 and has no authentication.

## Run it

```bash
make db-up         # SAMAY's own database (docs/docker-safety.md)
make db-migrate    # once, and after each new migration
make api           # http://127.0.0.1:8000, documentation at /api/docs (Ctrl-C to stop)
make db-down       # when finished; saved data is kept
```

## Demo with curl (from the repository folder, in a second terminal)

```bash
curl -s 127.0.0.1:8000/api/health

# 1-2: check a bill without saving it
curl -s -X POST --data-binary @examples/bills/differing.json 127.0.0.1:8000/api/validate

# 3-5: calculate, reconcile against the printed values, save input and report
curl -s -X POST --data-binary @examples/bills/differing.json 127.0.0.1:8000/api/runs

# 6: history and one saved report
curl -s 127.0.0.1:8000/api/runs
curl -s 127.0.0.1:8000/api/runs/1
curl -s 127.0.0.1:8000/api/runs/1/report      # exactly as saved
curl -s 127.0.0.1:8000/api/runs/1/source      # the bill file exactly as sent

# 7: recalculate from the saved file and compare with the saved report
curl -s -X POST 127.0.0.1:8000/api/runs/1/verify
```

`examples/bills/missing-data.json` shows MISSING values (totals `null`, with reasons in
the report); `examples/bills/matching.json` gives a clean reconciliation.

## Responses

A saved run's summary:

```json
{
  "run_id": 1, "bill_id": "EXAMPLE-DIFFERING", "command": "reconcile",
  "exit_code": 1, "outcome": "not-clean", "outcome_text": "...",
  "tariff": {"id": "SAMAY-DEMO-1", "status": "synthetic"}, "synthetic": true,
  "totals": {
    "calculated": {"paise": "112606000", "inr": "₹11,26,060.00"},
    "printed": {"paise": "112606000", "inr": "₹11,26,060.00"},
    "difference": {"paise": "0", "inr": "₹0.00"}
  },
  "explanation": "complete", "created_at": "2026-11-07T10:00:00+00:00"
}
```

- Money is a string of paise plus a display string, never a JSON number. `null`
  means MISSING or not determinable; the report says why.
- `outcome` is `clean`, `not-clean` (a line differs or could not be compared, or the
  totals differ or cannot be determined) or `calculated`. `not-clean` is a result,
  not an error: the run is saved and the answer is 201.
- `report` is the full `samay.report/1` document ([json-format.md](json-format.md)).

Errors: 422 invalid bill (the validation document lists every problem), 404 unknown
run, 503 database not running or not configured, 500 SAMAY bug (no details). Nothing
is saved on any error.
