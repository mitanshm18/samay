# Technical debt and backlog

Findings from the adversarial review of PR #2 (Milestone 1, Step 2), 6 Nov 2026.
None of these produces a wrong financial result; each was checked for that before
being deferred. The Major finding (shared decimal context) and a second silent
double-rounding path in `round_paise` were fixed in PR #2 itself.

Severity: **Minor** = should fix, low risk; **Suggestion** = optional improvement.

| # | Severity | Area | Item | Proposed fix | Target |
| --- | --- | --- | --- | --- | --- |
| 2 | Minor | Money, units | Absurd inputs (e.g. `Money.from_rupees("1e1000000")`, 150-digit amounts, `round_paise(Decimal("1e200"))`) raise Python `decimal` exceptions instead of `SamayCoreError`. They still fail closed and never round. | Check magnitude and digit count before arithmetic; convert to `InvalidValueError` / `PrecisionError`. | Done in Step 3A: input digit and exponent limits, magnitude checks before arithmetic, `round_paise` size guard. |
| 3 | Minor | Provenance | A value calculated from an ESTIMATED input reads `calculated · verified`; the estimate is only visible through `leaves()`. | Add `rests_on_estimate`, spreading like SYNTHETIC. | Done in Step 3A: `Traced.rests_on_estimate`. |
| 4 | Minor | Property tests | Two properties recompute the implementation's own formula (`rate × kWh`, `kWh / kVAh`). | Use `fractions.Fraction` as an independent oracle. | Done in Step 3A: bill property tests use an independent `Fraction` oracle. |
| 5 | Minor | Property tests | The rounding property cannot tell HALF_UP from HALF_EVEN and rarely generates exact .5 ties (covered only by example tables). | Add symmetry and monotonicity properties and a tie-forcing generator. | Done in Step 3A: tie generators (paisa ties tell HALF_UP from HALF_EVEN; half-rupee bill totals, both signs), symmetry and monotonicity properties. |
| 6 | Minor | Provenance | With several MISSING inputs, the derived note names only the first. | List all missing inputs. | Done in Step 3A: all missing inputs are named; `missing_reasons()`. |
| 7 | Minor | Public API | `Traced.missing()` returns `Traced[Any]`, losing the value type for mypy. | Optional type argument or typed overload. | Done in Step 3A: `Traced.missing(..., kind=Energy)` overload. |
| 8 | Suggestion | Rounding | HALF_UP rounds ties away from zero (-12.5 → -13); some systems round towards +∞. | Confirm the convention for credits against the UP tariff order (24-row checklist). | Tariff verification |
| 9 | Suggestion | Units | `Energy / Duration → Power` (average demand) is valid but refused. | Add with explicit rounding when needed. | When needed |
| 10 | Suggestion | Money | `Rate` per kVA has no billing-period basis (per month vs per period). | Make the basis explicit in the tariff model. | Done in Step 3A: `RateBasis` on `Rate`. |
| 11 | Suggestion | Public API | Quantity's private `_value` can be reassigned (immutable by convention only). | Block `__setattr__` after `__init__`. | Step 3B |
| 12 | Suggestion | Public API | `Traced` accepts mutable or unhashable raw values; it is only shallowly frozen. | Document or check that raw values are immutable. | Step 3B |
| 13 | Suggestion | Provenance | `Traced.leaves()` is recursive (limit about 1,000 levels). | Iterative walk. | When needed |
| 14 | Suggestion | CI | GitHub Actions pinned to major tags, not commit SHAs. | Pin to SHAs. | Before freeze (1 Dec) |

Numbering follows the review document; #1 was the Major finding (fixed).
Items marked "Done in Step 3A" stay listed until Step 3A is merged, then move to the
changelog of that pull request.

## PR #3 review (Step 3A), 6 Nov 2026

Verdict SAFE TO MERGE; the four Minor findings were fixed in PR #3 itself.

| # | Item | Fix |
| --- | --- | --- |
| M1 | A tariff with 6-decimal rates could pass validation and fail mid-bill with PrecisionError. A property test added for the fix also found a too-large excess rate failing mid-bill. | Precision and size budget checked when the tariff is created (decision 0003, item 11). |
| M2 | ToD rate billing basis not validated. | ToD rates must be `PER_UNIT`. |
| M3 | An empty "taken as printed" total was an invented ENTERED zero. | It is MISSING with a reason. |
| M4 | Estimated inputs untested in billing. | Tests, `rests_on_estimate` / `estimate_bases` on lines and breakdown, `input-estimated` warning. |

Open suggestions from that review, not done: S1 `ExactApparentPower ==` vs ordering,
S2 input digit limit counts trailing zeros (and its message), S3 warn on identical
repeated `other` lines, S4 `Rate.scaled` accepts negative multipliers, S5 test helper on
`mypy_path`, S6 oracle covers complete data only.

## Step 3B, 6 Nov 2026

| Item | Status |
| --- | --- |
| `input-estimated` warning for estimated printed lines and printed totals (D10) | Done in Step 3B |
| PRINTED_ONLY status (D2) | Deferred: unreachable while every printed line has a known code; revisit if free-text printed lines are accepted |
| `cli._banner` repeats the banner text built inside `recompute_bill` (which 3B may not change) | A test keeps them equal; share one function when `recompute.py` is next changed |
| Suggestions #11 and #12 (immutability of quantities and `Traced` raw values) | Not done in 3B (outside the approved scope); still open |
