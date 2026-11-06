# 0005: Saving bills and reports (Milestone 1, Step 4)

Status: accepted, 7 Nov 2026. Trimmed Step 4 scope approved on 6 Nov 2026.

## Context

The 10 November demo must save a checked bill and show it again later: enter or
upload a bill, calculate, reconcile, save the exact input and report, retrieve and
display them. Steps 5 and 6 (API and front end) build on this. The financial rules
of decisions 0002 to 0004 must survive storage unchanged.

## Decisions

1. **The database stores results; it never calculates.** `samay.db.save_bill` runs
   the same path as `python -m samay.cli` (`load_bill` → `recompute_bill` →
   `reconcile` → `samay.report/1`) and stores what it produced. There is no money
   arithmetic in `samay/db` or in SQL, except one CHECK that re-states an identity.
2. **One-way dependency.** `samay.db` imports the engine; `core`, `tariffs`,
   `billing`, `io` and `cli.py` never import `samay.db`, SQLAlchemy, psycopg or
   Alembic (`tests/test_boundaries.py`). `core` stays standard-library only.
3. **Two append-only tables.**

   | Table | Holds |
   | --- | --- |
   | `bill_document` | the exact bytes of a `samay.bill/1` file (`bytea`, not JSONB, so nothing is reordered or normalised), its SHA-256 (unique: the same file is stored once), bill and tariff id |
   | `calculation_run` | one calculate or reconcile of a stored file: the exact report text and its SHA-256, exit code, tariff id, name and status (synthetic or verified), engine version, and copies of the totals for listing |

   A per-line table was left out: the report already holds every line, and nothing
   in the demo queries lines across bills.
4. **Money is BIGINT paise. MISSING is NULL, never 0.** The three total columns
   (`calculated_total_paise`, `printed_total_paise`, `total_difference_paise`) are
   nullable with no default. NULL means MISSING, not determinable, or (printed
   total only) not given; the report text says which. A test fails on any
   `real`, `double precision`, `numeric` or `money` column.
5. **The report text is the record.** `show` returns it byte for byte. The total
   columns are copied from the engine's own objects and, before anything is
   written, compared with the same values parsed back from the report text
   (`ProjectionMismatchError` otherwise: nothing is saved).
6. **The database re-checks what it can.** CHECK constraints refuse:
   a difference other than printed − calculated when both are known, or a
   difference when either is unknown; printed values or an explanation on a
   calculate run; exit codes other than 0 (calculate) and 0/1 (reconcile);
   unknown command, explanation, tariff status or formats; malformed SHA-256s;
   an empty bill. Every comparison is guarded with `IS NOT NULL`, because a CHECK
   that evaluates to NULL passes (a test found this in the first draft).
7. **Saved records are immutable.** Triggers refuse UPDATE, DELETE and TRUNCATE on
   both tables, and the foreign key is `ON DELETE RESTRICT`. Checking a bill again
   adds a new run. `verify` recalculates a stored file and reports whether the
   report text is identical; it never writes.
8. **Atomic saves.** Document and run are written in one transaction; an invalid
   bill raises before the transaction starts, and any failure inside it rolls
   both back.
9. **Migrations are explicit and hand-written** (Alembic, `backend/migrations`).
   `make db-migrate` applies them; nothing migrates on start. The downgrade refuses
   while any record is saved. Tests prove upgrade → downgrade → upgrade on an empty
   database and that the models match the migration (`alembic check`).
10. **Local only.** The URL comes from `SAMAY_DATABASE_URL` or from `.env`
    (`SAMAY_DB_PASSWORD`, `SAMAY_DB_PORT`); any host other than 127.0.0.1,
    localhost or ::1 is refused, and the password is never printed.
11. **Tests never touch the `samay` database.** Each database test gets its own
    `samay_test_<random>` database (cloned from a migrated template) and drops it.
    `make backend-db-test` needs a running database: `samay-db` on the Mac, a
    `postgres:16` service container in CI. It has its own coverage gate (≥ 95% of
    `samay/db`); `make backend-test` stays Docker-free and omits `samay/db`.
12. **Dependencies:** SQLAlchemy 2.0, Alembic and psycopg 3 (binary wheel), as named
    in decision 0001. They live in `backend/.venv` only.

## Consequences

- A report saved today stays exactly as it was even if the engine changes;
  `verify` shows whether the current engine still agrees.
- A future schema change is a new hand-written migration; records are never
  rewritten in place.
- Step 5 (API) calls `save_bill`, `list_runs` and `get_run`; it adds no storage
  logic of its own.
