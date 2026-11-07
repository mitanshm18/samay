# Demo: setup, check and script

How to run the SAMAY Milestone 1 demo on the presenter's Mac. Everything runs locally:
SAMAY's own database in Docker (`samay-db` only), the API on 127.0.0.1:8000 and the web
page on 127.0.0.1:5173. Nothing is installed globally.

The tariff is **SAMAY-DEMO-1 (SYNTHETIC — not UP rates)**. Say so when presenting; every
run page also shows it.

## Before the day (once)

```bash
cd ~/Developer/samay
git checkout main && git pull --ff-only
cp -n .env.example .env        # if .env does not exist yet; see README.md
make doctor                    # read-only check
make check                     # backend checks (about 1 minute)
make web-install               # frontend packages into frontend/node_modules
make web-check                 # frontend type check, tests and build
```

`make db-up` refuses to start if free disk is below 20 GB.

## Start the demo (about 1 minute)

Three terminals in `~/Developer/samay`:

```bash
# terminal 1
make db-up && make db-migrate
make api                       # leave running

# terminal 2
make web                       # leave running

# terminal 3: rehearsal check
make demo-check
```

`make demo-check` sends every bill in `examples/bills` through the running app: validate,
calculate, reconcile, save, open, download the exact report and bill file, verify. It
checks that a MISSING total is never shown as an amount, that every cost optimisation
saving is labelled illustrative (synthetic tariff), and that the three golden bills
give the hand-checked totals and line statuses. It prints an `ok` line for the API, the web
page and each of the seven bills, and ends with `Demo check passed.` It saves one run per
bill, so after it the bill history has demo data, including GB2 and GB3; saving them again
live in the demo simply adds new runs. Run it before the audience arrives. Each repeat
adds seven more runs (saved runs are never edited or deleted).

Open http://127.0.0.1:5173. The status at the bottom of the sidebar (top right on a phone)
must say **API and database online**.

## Demo script (about 5 minutes)

1. **Dashboard.** "Every bill SAMAY has checked. Each run is saved exactly as entered and
   can be re-verified." Point at the counts: clean, needs review, calculated only.
2. **Check a bill → `golden-gb2.json` → Validate.** "Valid for tariff SAMAY-DEMO-1; the
   tariff is synthetic and labelled everywhere."
3. **Calculate, reconcile and save.** The run opens.
   - KPIs: total payable ₹8,87,581.00, printed total the same, difference ₹0.00.
   - Line by line: the energy charge is printed **1 paisa high** (red, *Differs*).
     Meter rent ₹1,250.00 is *Taken as printed*: SAMAY does not recalculate it and says so.
   - **Why the totals match**: +₹0.01 on the lines, −₹0.01 in the printed bill's own
     arithmetic. "A matching total does not mean matching lines. SAMAY checks to the paisa."
   - **Calculation breakdown**: every formula, input source and rounding rule.
   - **Cost optimisation** tab: the pink banner says every ₹ figure is illustrative
     (synthetic tariff). Largest opportunity: raise power factor 0.917 → 0.99,
     ₹53,072.00 per bill. Excess demand (337.125 kVA against 300 kVA contract):
     ₹38,981.00, *Actionable*, high confidence. Open **How this was worked out**: the
     scenario total, calculation basis, assumptions and confidence. "Each saving is
     the same calculator run on a what-if bill. Nothing is guessed; scenarios are not
     added together."
4. **Verify saved report.** "SAMAY recalculates from the saved bill and confirms the
   saved report is identical, byte for byte."
5. **Check a bill → `golden-gb3.json` → Calculate, reconcile and save.**
   - Total payable is **MISSING**, with the reason (off-peak kVAh not printed), never ₹0.
   - The ToD line is illegible on the printed bill: *Cannot compare*.
   - **Why the totals cannot be compared**: SAMAY does not guess.
   - **Cost optimisation**: "Insufficient data" instead of a saving; the time-of-day
     chart shows off-peak as MISSING.
6. **Check a bill → paste or upload a broken bill → Validate.** Every problem is listed
   with where it is; nothing is calculated or saved. (For example, delete the
   `"tariff_id"` line from a sample.)
7. **Dashboard** again: the new runs are at the top. Open any run, then **Report JSON** and
   **Bill file** to show the exact saved records.

Other sample bills: `missing-data` (ToD readings missing), `pass-through` (meter rent and
an estimated duty figure, tagged ESTIMATED), `differing`, `matching` (clean),
`golden-gb1` (excess demand line not printed).

## If something goes wrong

| What you see | Do this |
| --- | --- |
| "API or database offline" (top right) | Check terminal 1. Database stopped: `make db-up`. The badge turns green within 10 seconds; then reload the page. |
| "Cannot reach the SAMAY API. Start it with: make api" | Restart `make api` in terminal 1. |
| "Cannot reach SAMAY's database. Start it with: make db-up" | `make db-up`. Nothing was saved while it was down; try again. |
| Port 5173 or 8000 already in use | An old `make web` or `make api` is still running; stop it (Ctrl-C in its terminal). |
| `make demo-check` prints FAIL | Do not demo from this copy. Run `make check` and `make web-check`. |

Tested on 7 Nov 2026: with the database stopped, every database call returns 503 with
that message and saves nothing; validation still works; when the database is back the
API answers again without a restart.

## After the demo

```bash
# Ctrl-C in the make api and make web terminals, then:
make db-down                   # stops samay-db; the saved runs stay in samay_pgdata
```
