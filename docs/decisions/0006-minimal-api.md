# 0006: Minimal HTTP API (Milestone 1, Step 5)

Status: accepted, 7 Nov 2026. Scope approved on 6 Nov 2026 for the 10 November demo.

## Context

The demo front end (Step 6) needs to submit a bill, see it validated, calculated
and reconciled, have the exact input and report saved, and list, open and verify
saved results. Steps 3 and 4 already do all of this from the command line.

## Decisions

1. **A thin layer, no financial logic.** `samay.api` calls `load_bill`
   (validation) and `samay.db` (`save_bill`, `list_runs`, `get_run`,
   `verify_run`). It does no arithmetic on money; it only formats stored paise for
   display with `Money.format_inr`. The engine packages import neither FastAPI nor
   `samay.api`, and `samay.db` does not import the API (`tests/test_boundaries.py`).
2. **FastAPI, served by uvicorn on 127.0.0.1 only** (`make api`, port 8000), as
   named in decision 0001. No authentication: the server is local to the
   presenter's Mac and binds to the loopback address only.
3. **Bills are posted as the raw `samay.bill/1` JSON**, read up to the same
   1,000,000-byte limit as the command line, and checked by the same strict reader.
   The API never parses or re-serialises a bill itself, so the saved bytes are
   exactly what was sent.
4. **Endpoints**

   | Method and path | Does | Success |
   | --- | --- | --- |
   | `GET /api/health` | API and database status | 200 |
   | `POST /api/validate` | check a bill, save nothing (needs no database) | 200 |
   | `POST /api/runs?command=reconcile` | check, calculate, reconcile, save (`command=calculate` to recalculate only) | 201 |
   | `GET /api/runs?limit=50` | saved runs, newest first (1 to 500) | 200 |
   | `GET /api/runs/{id}` | summary and the saved report | 200 |
   | `GET /api/runs/{id}/report` | the saved `samay.report/1` text, byte for byte | 200 |
   | `GET /api/runs/{id}/source` | the saved bill file, byte for byte | 200 |
   | `POST /api/runs/{id}/verify` | recalculate from the saved file and compare; writes nothing | 200 |

   OpenAPI documentation is at `/api/docs`.
5. **Money is never a JSON number.** Summary totals are `{"paise": "112606000",
   "inr": "₹11,26,060.00"}` or `null` when MISSING or not determinable (the
   report gives the reasons). Reports are the stored `samay.report/1` documents,
   which hold no JSON numbers. Only `run_id` and `exit_code` are numbers.
6. **A reconciliation that is not clean is a result, not an error.** `POST /api/runs`
   answers 201 for every saved run, with `exit_code` (0 or 1, as decision 0004),
   `outcome` (`clean`, `not-clean` or `calculated`) and a plain-language
   `outcome_text`. The same wording is printed by `python -m samay.db save`, and
   `make bill-save` no longer reports exit 1 as a make error (exits 2 and 3 still
   fail). The reconciliation and its exit codes are unchanged.
7. **Errors**

   | Status | When | Body |
   | --- | --- | --- |
   | 422 | invalid bill (every problem listed), bad `command` or `limit` | `samay.report/1` validation document with `errors`, or FastAPI's parameter error |
   | 404 | unknown run id | `{"error": "run-not-found", ...}` |
   | 503 | database not running or not configured | `{"error": "database-unavailable" or "database-not-configured", "message": ...}` |
   | 500 | a SAMAY bug | `{"error": "internal-error", ...}` with the exception type only: no traceback or values |

   Nothing is saved on any error.
8. **Dependencies:** FastAPI and uvicorn (no extras) at run time; `httpx2` for
   FastAPI's test client in development only.
9. **Tests:** `tests/api` runs with the database tests (`make backend-db-test`,
   in CI's `database` job) against throwaway `samay_test_*` databases: invalid
   input, missing values (NULL, never 0), reconciliation differences, the golden
   bills, byte-exact report and source, verify, 404s, and database failures (503).

## Consequences

- The Step 6 front end only needs these eight endpoints, and a dev-server proxy
  to 127.0.0.1:8000 (so no CORS settings are needed).
- Exposing the API beyond the local machine would need authentication first; that
  is a separate decision.
