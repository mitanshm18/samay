# 0008: Cost optimisation engine and the redesigned demo UI

Status: proposed, 7 Nov 2026, for the 10 November demo.

## Context

Judges and plant engineers want to know not only whether the bill is right, but where
the next bill could cost less. SAMAY must not invent consumption data, tariff rates or
savings, and must never present a synthetic-tariff figure as a real saving.

## Decisions

1. **A pure engine next to the calculator.** `samay.optimise` takes a validated `Bill`
   and `Tariff` and returns an `OptimisationReport`. It has no database, API or UI
   imports (enforced by `tests/test_boundaries.py`) and does not change the bill
   calculation or reconciliation engines.
2. **Every ₹ figure is a recalculated scenario.** A saving is the current
   recalculated total minus the total of a scenario bill (for example: maximum demand
   held at contract demand) recalculated by the same `recompute_bill`, in integer
   paise. There is no separate savings formula and no float.
3. **Honest saving status.**
   - `illustrative`: the tariff is synthetic, or the bill's readings are synthetic. The
     UI says "Illustrative saving · synthetic tariff, not a real saving".
   - `estimated`: only for a verified tariff with sourced components and verified readings.
   - `insufficient-data`: an input or the bill total is MISSING; no amount is shown.
   - `not-applicable`: a finding with nothing to price.
4. **Kinds.** `actionable` (the bill itself shows the problem: excess demand, low power
   factor), `indicative` (a what-if whose size is a stated assumption: 10% peak shaving,
   10% load shift, a lower contract demand), `information`, and `insufficient-data`
   (for example, trends need earlier bills for the same meter). Every recommendation
   lists its calculation basis, assumptions, missing data and a confidence with a
   reason; confidence drops a level when an input is estimated.
5. **Scenarios are not additive.** Each saving is against the current bill alone; the
   UI says so next to the largest one.
6. **Nothing is saved.** `GET /api/runs/{id}/optimisation` analyses the saved bill file
   on demand; `POST /api/optimise` analyses a bill without the database.
7. **Charts size bars with `Number()`, nothing else.** Amendment to decision 0007: the
   history chart and gauges convert API strings to JavaScript numbers only to size bars
   and needles. Every number a person reads is the API's own text. The largest saving
   is chosen by comparing paise strings with `BigInt`, never by arithmetic.
8. **Redesign without new dependencies.** A dark control-room theme in plain CSS,
   hand-written SVG charts, and the same React, Vite and Zod stack. Run pages gain tabs
   (`#/runs/<id>`, `/optimisation`, `/calculation`); old links still work.

9. **Share of bill (7 Nov 2026, later).** Each saving also carries `share_of_bill`, the
   amount over the current total as text with one decimal place, worked out exactly
   in the backend from integer paise. The UI shows it; it does no arithmetic itself.
10. **Light, dark and system themes.** Same tokens, two palettes; the illustrative
    stamp (dashed, striped, pink) and the estimated stamp (solid, green) differ by
    shape as well as colour, so they stay distinct in both themes and in greyscale.

## Consequences

The demo shows illustrative savings with the synthetic tariff, clearly labelled. With a
verified tariff and verified readings the same code gives estimated savings. Trend and
anomaly detection across bills is reported as insufficient data until several bills for
one meter are saved.
