# Frontend

The SAMAY demo web page: a view over the local API ([../docs/api.md](../docs/api.md)).
It never calculates money; see [decision 0007](../docs/decisions/0007-demo-frontend.md).

## Run it

Needs Node.js 20 or newer. Packages install into `frontend/node_modules` only.

```bash
make db-up && make db-migrate   # SAMAY's database
make api                        # terminal 1: API on 127.0.0.1:8000
make web-install                # once
make web                        # terminal 2: open http://127.0.0.1:5173
make web-check                  # type check, tests, production build
```

## Screens

| Screen | Address | Uses |
| --- | --- | --- |
| Bill history | `#/` | `GET /api/runs` |
| Check a bill | `#/new` | `POST /api/validate`, `POST /api/runs?command=reconcile\|calculate` |
| Run report | `#/runs/<id>` | `GET /api/runs/<id>`, `POST /api/runs/<id>/verify`, report and bill downloads |

## Demo workflow

1. **Check a bill**: upload a `samay.bill/1` file, paste one, or pick a sample bill.
2. **Validate**: every problem is listed with its JSON path; nothing is saved.
3. **Calculate, reconcile and save**: SAMAY recalculates each line, compares it with
   the printed bill and saves the exact input and report.
4. The **run report** opens: total payable, printed total, difference, the line-by-line
   table (Match, Differs, Not on bill, Cannot compare, Taken as printed), why the
   totals differ, and the full calculation breakdown with formulas and assumptions.
5. **Verify saved report** recalculates from the saved bill and confirms the saved
   report is identical.
6. **Bill history** lists every saved run.

## Code

| Path | Purpose |
| --- | --- |
| `src/api.ts` | API client and Zod schemas (money must be digit strings) |
| `src/format.ts` | Text-only formatting of amounts, quantities and dates |
| `src/components/values.tsx` | Badges for MISSING, ESTIMATED, pass-through and synthetic |
| `src/pages/` | Dashboard, Check a bill, Run report |
| `src/test/fixtures/` | Responses captured from the real API for the tests |
