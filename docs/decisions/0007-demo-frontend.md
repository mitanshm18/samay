# 0007: Demo front end (Milestone 1, Step 6)

Status: proposed, 7 Nov 2026. Scope approved on 7 Nov 2026 for the 10 November demo.

## Context

The demo must show a bill being entered, validated, recalculated, reconciled with the
printed bill, saved and opened again. Step 5's API does all of this. The front end only
has to present it clearly to judges and plant engineers.

## Decisions

1. **A view over the API, with no financial logic.** Every amount comes from the API
   as a string of paise (`{"paise": "112606000", "inr": "₹11,26,060.00"}`) or as `null`.
   The page never adds, subtracts or rounds money, and never converts paise to a
   JavaScript number. `src/format.ts` groups digits as text; its tests check it
   against the backend's `Money.format_inr`, including values beyond 2^53.
2. **Missing is never zero.** A `null` amount or a MISSING value is shown as a
   MISSING badge with the reasons from the report. Pass-through lines are labelled
   "Taken as printed" and their difference "Not checked". Estimates carry an
   ESTIMATED badge. A synthetic tariff shows a banner on every run.
3. **Responses are checked with Zod.** Money must arrive as digit strings; a number
   or an unexpected shape is an error, not a guess.
4. **Existing endpoints only.** Dashboard: `GET /api/runs`. Check a bill:
   `POST /api/validate`, `POST /api/runs?command=reconcile|calculate`. Run report:
   `GET /api/runs/{id}`, `POST /api/runs/{id}/verify`, and links to
   `/api/runs/{id}/report` and `/source`.
5. **Minimal stack.** React 18, TypeScript, Vite, Zod, plain CSS and hash routing.
   No Tailwind, component library, query library or router: the demo has three
   screens. Tests use Vitest and Testing Library with fixtures captured from the
   real API. All versions are pinned in `package-lock.json`; `npm ci` installs into
   `frontend/node_modules` only.
6. **Local only.** The Vite dev server binds to 127.0.0.1:5173 and proxies `/api` to
   the API on 127.0.0.1:8000. No authentication, as in decision 0006.

## Consequences

- Changing a calculation never needs a front-end change; the page shows whatever
  lines the report contains.
- The architecture's earlier plan (Tailwind, Radix, TanStack Query) is dropped for
  Milestone 1. It can be revisited if the product grows beyond the demo.
