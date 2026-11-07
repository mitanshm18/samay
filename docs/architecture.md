# Architecture

SAMAY is a modular monolith: one backend, one front end, one database.

```
frontend/  React + TypeScript + Vite (npm), Zod; plain CSS (decision 0007)
    |  HTTP (JSON, validated on both sides)
backend/   FastAPI (Python 3.13, uv)
    |-- core/      pure calculation code: no I/O, no database, fully unit-tested
    |-- tariffs/   tariff definitions, each marked synthetic or verified
    |-- billing/   bill input, validation, recalculation and reconciliation (uses core + tariffs)
    |-- io/        strict JSON bill reader and report writer (samay.bill/1, samay.report/1)
    |-- cli.py     python -m samay.cli validate|calculate|reconcile
    |-- api/       HTTP API over db/ (FastAPI, 127.0.0.1 only; make api; see api.md)
    `-- db/        saved bills and reports: SQLAlchemy models, save/list/show/verify
                   (python -m samay.db); migrations in backend/migrations (Alembic, psycopg)
PostgreSQL 16 in Docker Compose project "samay" (127.0.0.1:55432)
```

## The calculation core (`backend/src/samay/core`)

Pure Python, standard library only: no I/O, database, network or clock access.

| Module | Holds |
| --- | --- |
| `money.py` | `Money` (int paise), `ExactAmount` (exact fractional paise), `Rate` (exact paise per unit, with a `RateBasis`) |
| `rounding.py` | `RoundingRule`, `round_paise`: the only place money is rounded |
| `units.py` | `Energy` kWh, `ApparentEnergy` kVAh, `ReactiveEnergy` kVArh, `Power` kW, `ApparentPower` kVA, `Duration` h, `PowerFactor`, `ExactApparentPower` (exact kVA, e.g. a 75% demand floor) |
| `measurement.py` | `MeterInterval`, `IntervalReading`, `average_power_factor` |
| `provenance.py` | `Provenance`, `DataStatus`, `Traced` |

Rules the code enforces (and tests prove):

- Money is integer **paise**. Binary floats are refused everywhere.
- Decimal arithmetic never uses Python's shared decimal context, so other code changing
  `decimal.getcontext()` cannot alter any result (decision 0002, rule 10).
- `Rate x quantity` gives an `ExactAmount`; it becomes `Money` only via `.round(rule)`
  with an explicit `RoundingRule`. There is no default and no implicit rounding.
  See [decisions/0002-money-and-rounding.md](decisions/0002-money-and-rounding.md).
- Quantity types cannot be mixed (runtime `UnitMismatchError`, and mypy flags it too),
  are never negative, and hold at most 3 decimal places: excess precision is refused,
  never rounded silently.
- A power factor comes only from `average_power_factor()`, given kWh and kVAh readings
  for the same meter and the same interval, with consistent data (kVAh > 0, kWh <= kVAh).
  It is an exact fraction until rounded explicitly.
- Every value can carry provenance (`entered`, `extracted`, `calculated`, `estimated`,
  `missing`) and a separate data status (`synthetic` or `verified`). Synthetic status
  always spreads to derived values; missing inputs make results missing.
- `recompute_bill(bill, tariff)` (Step 3A, `samay/billing`) validates the input, then
  computes every line exactly and rounds each once; total = sum of lines, always.
  See [decisions/0003-tariff-and-bill-model.md](decisions/0003-tariff-and-bill-model.md).
- `reconcile(bill, breakdown)` (Step 3B) compares each recalculated line with the
  printed bill (MATCH, DIFFERS, CALCULATED_ONLY, CANNOT_COMPARE, NOT_RECALCULATED; zero
  tolerance) and the totals independently, and never changes either side. See
  [decisions/0004-reconciliation-json-cli.md](decisions/0004-reconciliation-json-cli.md),
  [json-format.md](json-format.md) and [cli.md](cli.md).
- `samay.db` (Step 4) saves the exact bill file and the exact report in two
  append-only tables; money is BIGINT paise and MISSING is NULL. The engine never
  imports it. See [decisions/0005-persistence.md](decisions/0005-persistence.md).
- `samay.api` (Step 5) is a thin FastAPI layer over `samay.db`: no money arithmetic,
  money as strings of paise, MISSING as null. See
  [decisions/0006-minimal-api.md](decisions/0006-minimal-api.md) and [api.md](api.md).
- `frontend/` (Step 6) shows what the API returns. It does no arithmetic on money and
  formats amounts from the paise strings as text. See
  [decisions/0007-demo-frontend.md](decisions/0007-demo-frontend.md).
- The schedule optimiser (later milestone) is exhaustive and bounded: at most 8 movable
  batches, 2,000,000 combinations and 10 seconds.

## Tariffs

- `SAMAY-DEMO-1 (SYNTHETIC — not UP rates)` is used in Milestone 1. Its rules are in
  [tariffs/SAMAY-DEMO-1.md](tariffs/SAMAY-DEMO-1.md).
- A verified UP HV-2 tariff is added only after the 24-row checklist is complete,
  with a page and clause reference, interpretation, unit and an independently checked
  example for every rule. See [data-policy.md](data-policy.md).

## Later milestones

PDF reports use ReportLab. End-to-end tests use the Playwright Chromium headless shell only.
Deliberately not used: pre-commit framework, pandas, OR-Tools, WeasyPrint. See
[decisions/0001-lean-stack.md](decisions/0001-lean-stack.md).
