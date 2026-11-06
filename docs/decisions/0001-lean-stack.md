# 0001: Lean stack

Status: accepted (Milestone 1 proposal, section 3)

## Context

Development happens on a MacBook Air with about 29 GB free and other Docker projects
that must not be disturbed. The calculations must be deterministic and testable, and the
project should be clear enough to serve as a portfolio piece.

## Decision

- Backend: FastAPI, Python 3.13 via uv (no Python downloads), SQLAlchemy, Alembic, psycopg.
- Front end: React, TypeScript, Vite, npm, Tailwind, Radix, TanStack Query, Zod.
- Database: PostgreSQL 16 in an isolated Compose project, reusing the existing image.
- Reports: ReportLab. Browser tests: Playwright Chromium headless shell only.
- Optimiser: exhaustive search with hard limits (8 batches, 2,000,000 combinations, 10 s).

## Not used, and why

| Tool | Reason |
| --- | --- |
| pandas | Large; the data is small and integer-paise maths is clearer without it |
| OR-Tools | Large; exhaustive search is exact and explainable at this size |
| WeasyPrint | Needs system libraries; ReportLab is pure Python |
| pre-commit framework | Downloads tool environments; `make check` and CI cover it |
| pnpm | npm is already installed |

## Consequences

Total footprint stays around 1.5 to 2.5 GB. If the optimiser needs larger problems later,
the limits are explicit and the decision can be revisited.
