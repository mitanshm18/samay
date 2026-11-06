# Architecture

SAMAY is a modular monolith: one backend, one front end, one database.

```
frontend/  React + TypeScript + Vite (npm), Tailwind, Radix, TanStack Query, Zod
    |  HTTP (JSON, validated on both sides)
backend/   FastAPI (Python 3.13, uv)
    |-- core/      pure calculation code: no I/O, no database, fully unit-tested
    |-- tariffs/   tariff definitions, each marked synthetic or verified
    |-- api/       HTTP routes
    `-- db/        SQLAlchemy models + Alembic migrations (psycopg)
PostgreSQL 16 in Docker Compose project "samay" (127.0.0.1:55432)
```

## The calculation core

- Money is stored as integer **paise**. Floats never hold money.
- Quantities carry units (kWh, kVAh, kVA, kW, hours) that cannot be mixed by accident.
- Every value carries a provenance tag: `extracted`, `entered`, `calculated`,
  `estimated` or `missing`.
- `recompute_bill(inputs, tariff)` rebuilds a bill line by line from tariff rules.
- `reconcile(printed_bill, recomputed)` explains each difference.
- The schedule optimiser is exhaustive and bounded: at most 8 movable batches,
  2,000,000 combinations and 10 seconds. It refuses larger problems rather than guessing.

## Tariffs

- `SAMAY-DEMO-1 (SYNTHETIC — not UP rates)` is used in Milestone 1.
- A verified UP HV-2 tariff is added only after the 24-row checklist is complete,
  with a page and clause reference, interpretation, unit and an independently checked
  example for every rule. See [data-policy.md](data-policy.md).

## Later milestones

PDF reports use ReportLab. End-to-end tests use the Playwright Chromium headless shell only.
Deliberately not used: pre-commit framework, pandas, OR-Tools, WeasyPrint. See
[decisions/0001-lean-stack.md](decisions/0001-lean-stack.md).
