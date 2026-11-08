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
| Run report: reconciliation | `#/runs/<id>` | `GET /api/runs/<id>`, `POST /api/runs/<id>/verify`, report and bill downloads |
| Run report: cost optimisation | `#/runs/<id>/optimisation` | `GET /api/runs/<id>/optimisation` |
| Run report: calculation | `#/runs/<id>/calculation` | the same run document |

## Demo workflow

1. **Check a bill**: upload a `samay.bill/1` file, paste one, or pick a sample bill.
   `golden-gb1` to `golden-gb3` are the three bills checked by hand.
2. **Validate**: every problem is listed with its JSON path; nothing is saved.
3. **Calculate, reconcile and save**: SAMAY recalculates each line, compares it with
   the printed bill and saves the exact input and report.
4. The **run report** opens: total payable, printed total, difference, the line-by-line
   table (Match, Differs, Not on bill, Cannot compare, Taken as printed), why the
   totals differ, and the full calculation breakdown with formulas and assumptions.
5. The **Cost optimisation** tab shows demand, time-of-day energy, power factor and
   load factor, and recommendations (actionable, indicative, information,
   insufficient data) with the saving, confidence and how it was worked out. With
   the synthetic tariff every ₹ figure is labelled illustrative, not a real saving
   ([decision 0008](../docs/decisions/0008-cost-optimisation.md)).
6. **Verify saved report** recalculates from the saved bill and confirms the saved
   report is identical.
7. **Bill history** lists every saved run, with a chart of recent totals (a MISSING
   total is drawn hatched, never as zero).

**Themes.** The switcher at the bottom of the sidebar (top right on a phone) offers
Light, Dark and System. The choice is saved in the browser (`localStorage`, key
`samay-theme`) and applied by a small script in `index.html` before the first paint,
so the page does not flash the wrong theme. Both themes share one set of CSS
variables in `src/styles.css`; the light theme uses darker colours so text keeps at
least 4.5:1 contrast on white.

**Dashboard.** The audit (what the bills say) and the optimisation insight (where the
next bill could cost less, for the latest run) are separate, labelled zones. The
chart of recent totals has a tooltip on hover or keyboard focus with the API's own
total, printed total and difference.

**Savings labels.** Illustrative savings (synthetic tariff) carry a dashed, striped
pink stamp and a dashed underline; estimated savings (verified tariff and readings) a
solid green stamp; insufficient data an amber stamp and the list of what is missing.
Each saving shows its share of the bill, worked out by the backend.

The charts are hand-written SVG and CSS. They convert API strings with `Number()` only
to size bars and needles; every number shown is the API's own text.

## Code

| Path | Purpose |
| --- | --- |
| `src/api.ts` | API client and Zod schemas (money must be digit strings) |
| `src/format.ts` | Text-only formatting of amounts, quantities and dates |
| `src/components/values.tsx` | Badges for MISSING, ESTIMATED, pass-through and synthetic |
| `src/pages/` | Dashboard, Check a bill, Run report |
| `src/test/fixtures/` | Responses captured from the real API for the tests |
