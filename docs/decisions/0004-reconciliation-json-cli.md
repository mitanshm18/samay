# 0004: Reconciliation, JSON files and command line (Milestone 1, Step 3B)

Status: accepted, 6 Nov 2026. Approved decisions D1 to D10 from the Step 3B plan,
with the clarifications given at approval.

## Context

Step 3A recalculates a bill (`recompute_bill`). Step 3B compares that recalculation
with the printed bill, reads and writes bills as JSON, and adds a command line. Every
guarantee from decisions 0002 and 0003 still holds: no floats, money in integer paise,
explicit rounding only, missing is never zero, no silent adjustment, pass-through lines
stay NOT_RECALCULATED, total = exact sum of the displayed lines, synthetic status
always spreads. Step 3B changes no formula, no tariff and nothing in `core/` or
`recompute.py`.

## Decisions

1. **Line statuses.** Each recalculated line gets one status:

   | Status | When | Difference (printed − calculated) |
   | --- | --- | --- |
   | `MATCH` | both amounts known and equal | 0 paise |
   | `DIFFERS` | both known, not equal | the exact difference in paise |
   | `CALCULATED_ONLY` | SAMAY has the line (even with a MISSING amount), the printed bill does not (D1) | not determinable |
   | `CANNOT_COMPARE` | the line is printed, but the printed or the calculated amount is MISSING | not determinable |
   | `NOT_RECALCULATED` | a printed `other` line, taken as printed and not checked | not determinable |

   Tolerance is zero: one paisa is a difference. A line absent from the printed bill is
   never a match, and its difference is never "minus the calculated amount" or zero (D1).
2. **No PRINTED_ONLY (D2).** Every printed line has a known code, so a printed line
   SAMAY does not calculate is always an `other` line. An unknown code is an input error
   (`unknown-line-code`): it is always reported and never dropped or guessed.
3. **Total and explanation are separate (D3).** The total comparison P − C is made
   whenever both totals are known, whatever the lines say. Separately the line
   explanation is `COMPLETE` (every recalculated line compared and every taken-as-printed
   amount known), `PARTIAL` (some lines compared) or `UNDETERMINABLE` (none). A matching
   total never implies matching lines, and the reverse. There is no "unattributed
   remainder" in PARTIAL. The printed-lines residual R = P − Σ printed lines is reported
   on its own. In COMPLETE, P − C = Σ line differences + R is checked as an invariant;
   a failure is a SAMAY bug (`ReconciliationInvariantError`), never an input error.
4. **One data status per file (D4).** `data_status` (`synthetic` or `verified`) is a
   required top-level key and applies to every value in the file. With SAMAY-DEMO-1 the
   results are synthetic whatever the file says.
5. **All errors at once (D5).** The reader collects every field-level problem with its
   JSON path and an error code. Malformed JSON syntax is one error. Only SAMAY's own
   input errors are input errors; anything else is a bug and exits 3.
6. **Provenance in output (D6).** Every amount and measurement in a report carries
   provenance, data status, note, missing reasons, estimate flags and the leaves it rests
   on. Counts and status labels are plain metadata.
7. **Exit codes (D7).** 0 = valid (validate, calculate) or a clean reconciliation;
   1 = reconcile found a difference, an uncompared line or an undeterminable total;
   2 = invalid input or usage; 3 = internal error. `reconcile` exits 0 only when every
   recalculated line matches, the totals agree and nothing is left undetermined.
8. **Golden bills (D8).** Three bills, worked out by hand by an independent checker.
   Expected values come only from the checker's signed worksheets. A CI step fails until
   all three are filled in and signed. Printed variants for the reconciliation check are
   built from the checker's values with documented changes (`tests/golden/test_golden.py`).
9. **Output streams (D9).** Results go to stdout as text or JSON. In JSON mode stdout
   holds one JSON document and nothing else; the synthetic banner, warnings and errors
   are inside it. In text mode, input errors go to stderr.
10. **Estimated printed values (D10).** An estimated printed line or total gets an
    `input-estimated` warning, is still compared, and its comparison is flagged
    `rests_on_estimate`.

## Consequences

- JSON numbers are refused everywhere: every amount and measurement is a decimal
  string, so no value passes through a float. See [../json-format.md](../json-format.md).
- The command line is described in [../cli.md](../cli.md).
