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

## The calculation core (`backend/src/samay/core`)

Pure Python, standard library only: no I/O, database, network or clock access.

| Module | Holds |
| --- | --- |
| `money.py` | `Money` (int paise), `ExactAmount` (exact fractional paise), `Rate` (exact paise per unit) |
| `rounding.py` | `RoundingRule`, `round_paise`: the only place money is rounded |
| `units.py` | `Energy` kWh, `ApparentEnergy` kVAh, `ReactiveEnergy` kVArh, `Power` kW, `ApparentPower` kVA, `Duration` h, `PowerFactor` |
| `measurement.py` | `MeterInterval`, `IntervalReading`, `average_power_factor` |
| `provenance.py` | `Provenance`, `DataStatus`, `Traced` |

Rules the code enforces (and tests prove):

- Money is integer **paise**. Binary floats are refused everywhere.
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
- Planned for Step 3: `recompute_bill(inputs, tariff)` and `reconcile(printed, recomputed)`.
- The schedule optimiser (later milestone) is exhaustive and bounded: at most 8 movable
  batches, 2,000,000 combinations and 10 seconds.

## Tariffs

- `SAMAY-DEMO-1 (SYNTHETIC — not UP rates)` is used in Milestone 1.
- A verified UP HV-2 tariff is added only after the 24-row checklist is complete,
  with a page and clause reference, interpretation, unit and an independently checked
  example for every rule. See [data-policy.md](data-policy.md).

## Later milestones

PDF reports use ReportLab. End-to-end tests use the Playwright Chromium headless shell only.
Deliberately not used: pre-commit framework, pandas, OR-Tools, WeasyPrint. See
[decisions/0001-lean-stack.md](decisions/0001-lean-stack.md).
