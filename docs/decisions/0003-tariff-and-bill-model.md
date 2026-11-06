# 0003: Tariff and bill model (Milestone 1, Step 3A)

Status: accepted, 6 Nov 2026. Approved decisions D1 to D9 from the Step 3 plan.

## Context

Step 3 recalculates an HT industrial bill from meter readings and a tariff, then (in
3B) compares it with the printed bill. No real UP tariff is verified yet, so the only
tariff is the synthetic SAMAY-DEMO-1.

## Decisions

1. **Two parts (D1).** 3A: tariff model, synthetic tariff, bill input, validation and
   recalculation. 3B: reconciliation, JSON command line and golden bills.
2. **Tariffs are typed Python dataclasses (D2)** in `samay/tariffs`, not a file format.
   A `Tariff` validates itself when created. A VERIFIED tariff must give a `SourceRef`
   (document and location) for every component; a SYNTHETIC one may not claim any.
3. **Rounding (D4).** Each money line is computed exactly and rounded once with the
   tariff's `line_rounding` (HALF_UP_PAISA for SAMAY-DEMO-1). Duty is a percentage of
   the *rounded* charge lines. The payable total is rounded with `total_rounding`
   (HALF_UP_RUPEE), and the difference is its own "rounding off" line.
4. **Every line appears once and total = sum of lines.** The subtotal (C8) is not a line.
   The engine checks `total = subtotal + rounding off = sum of lines` on every bill and
   raises `BillInvariantError` if it ever fails.
5. **Billing demand is exact.** `ApparentPower.percent()` returns an `ExactApparentPower`
   (up to 9 places), so 75% of 100.123 kVA stays 75.09225 kVA. Only money is rounded.
6. **Missing is never zero.** A missing reading makes every line that needs it MISSING,
   and then the subtotal, rounding off and total. Without ToD zone readings the ToD
   adjustment is MISSING, not 0.
7. **Printed lines are tagged by the user (D6).** Lines tagged `other` are included in
   the total as printed (`NOT_RECALCULATED`) and keep their own provenance. Lines with a
   calculated code are kept for 3B and do not change the recalculation.
8. **Assumptions are data.** Each component lists the assumptions it rests on; the
   breakdown lists them all once.
9. **Validation before calculation.** ERROR issues (kWh above kVAh, zones that do not
   add up to kVAh, partial zones already above kVAh, duplicate printed codes, zero
   contract demand) stop the calculation. WARNING issues (missing inputs, unusual
   period length, synthetic tariff) travel with the result.
10. **Rate basis (backlog #10).** `Rate` carries a `RateBasis`: the demand rate is
    `PER_UNIT_PER_BILLING_PERIOD`. There is no proration by period length.

11. **Supported rate precision is checked when a tariff is created (review M1).** SAMAY
    never rounds an intermediate value, so a tariff is refused up front if any charge
    could need more places than the exact types hold:

    | Parameter | Limit |
    | --- | --- |
    | Any rate | at most 6 decimal places of paise (₹0.000001 per 100) and below 1E+9 paise |
    | Demand floor % | at most 2 decimal places |
    | Duty % | at most 6 decimal places |
    | Excess multiplier | at most 3 decimal places |
    | Demand rate + floor % | rate places + floor places + 5 <= 12 (billing demand can have 3 + floor + 2 places) |
    | Demand rate x excess multiplier | must be a valid rate: rate places + multiplier places <= 6, below 1E+9 paise |

    Energy and ToD charges (rate <= 6 places x kVAh 3 places = 9) and duty (paise x
    percent / 100 <= 8 places) always fit. Trailing zeros do not count. A tariff that is
    accepted therefore never fails part-way through a bill because of its own precision;
    a property test checks this against an independent Fraction calculation. (Absurdly
    large *inputs* can still be refused with InvalidValueError; that is an input error.)
12. **ToD rates are per kVAh used (review M2).** A ToD rate must be `RateBasis.PER_UNIT`.
13. **Nothing is labelled ENTERED unless someone entered it (review M3).** With no printed
    `other` lines, `not_recalculated_total` is MISSING ("nothing was taken as printed"),
    never an invented zero. An absent printed total stays `None`.
14. **Estimates are visible (review M4).** Lines and the breakdown expose
    `rests_on_estimate` and `estimate_bases` (the stated basis of each estimate), and
    validation adds an `input-estimated` warning for each estimated reading.

## Consequences

- Adding a real tariff means writing a `Tariff` value with a source for every component
  and an independently checked example, per [data-policy.md](../data-policy.md).
- A tariff with a different structure (slabs, PF rebates, fixed charges) needs new
  fields and engine code; SAMAY-DEMO-1's shape is not assumed to match UP rules.
