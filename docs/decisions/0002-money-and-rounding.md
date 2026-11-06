# 0002: Money, rounding and units

Status: accepted (Milestone 1, Step 2 plan, approved 6 Nov 2026)

## Context

Every rupee SAMAY shows must be reproducible by hand from the tariff and the inputs.
Binary floating point cannot represent most rupee amounts exactly (0.1 + 0.2 != 0.3),
and silent rounding makes bills impossible to reconcile line by line.

## Decision

1. **Money is an int number of paise.** Floats are refused at every entry point.
2. **Rates are exact Decimals** in paise per unit (up to 6 decimal places), tied to one unit.
3. **Rate x quantity is an `ExactAmount`, not Money.** It becomes Money only via
   `ExactAmount.round(rule)`. Percentages (`Money.apply_percent`) also need a rule.
4. **Rounding rules are named:** `HALF_UP_PAISA`, `HALF_EVEN_PAISA`, `HALF_UP_RUPEE`,
   `CEIL_PAISA`, `FLOOR_PAISA`. HALF_UP rounds ties away from zero.
5. **Synthetic tariff line items use `HALF_UP_PAISA`. This is an assumption**, labelled as
   such. The rule for the real UP HV-2 tariff comes from the tariff order and the
   24-row checklist.
6. **Splitting money** uses largest remainder, so parts always add up exactly.
7. **Quantities** (kWh, kVAh, kVArh, kW, kVA, h) are separate types with at most 3 decimal
   places. More precision is refused, not rounded. Derived quantities that are not exact at
   3 places (for example 1.001 kW x 0.333 h) are refused unless the caller rounds
   explicitly with `energy_over(..., rounding=...)`.
8. **Power factor** is computed only from kWh and kVAh readings for the same meter and
   interval, with kVAh > 0 and kWh <= kVAh. It is held as an exact fraction; rounding it
   for display or a tariff threshold is a separate, explicit step.
9. **Provenance and data status are separate.** A calculated value can also be synthetic.
10. **The core never uses Python's shared decimal context.** Decimal operators such as `+`,
    unary `-`, `abs()` and `scaleb()` follow the thread's current context, which any code can
    change (`decimal.getcontext().prec = 4`). All core arithmetic is therefore done through two
    private contexts with fixed settings: `EXACT` (precision 100, raises instead of rounding)
    and `ROUNDING` (used only by `quantize` with the caller's named rule). Regression tests run
    the core under hostile shared contexts and require identical results, and the test suite
    fails any test that leaks a modified context. (Added after the PR #2 review: with precision
    4, ₹7.355/kWh × 1,234.567 kWh had silently become 908,343 paise instead of 908,024.)
11. **Rounding happens exactly once.** `round_paise` divides with `EXACT`, so an amount with
    more digits than the core can hold raises `PrecisionError` instead of being pre-rounded
    (which could turn 12.4999… into 12.5 and then 13). `ExactAmount` holds at most 12 decimal
    places of paise.

## Consequences

Tariff code in Step 3 must state a rounding rule for every line, which makes each rule
visible and testable. Callers that receive a `PrecisionError` must decide how to round,
rather than the core deciding for them.
