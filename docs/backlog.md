# Technical debt and backlog

Findings from the adversarial review of PR #2 (Milestone 1, Step 2), 6 Nov 2026.
None of these produces a wrong financial result; each was checked for that before
being deferred. The Major finding (shared decimal context) and a second silent
double-rounding path in `round_paise` were fixed in PR #2 itself.

Severity: **Minor** = should fix, low risk; **Suggestion** = optional improvement.

| # | Severity | Area | Item | Proposed fix | Target |
| --- | --- | --- | --- | --- | --- |
| 2 | Minor | Money, units | Absurd inputs (e.g. `Money.from_rupees("1e1000000")`, 150-digit amounts, `round_paise(Decimal("1e200"))`) raise Python `decimal` exceptions instead of `SamayCoreError`. They still fail closed and never round. | Check magnitude and digit count before arithmetic; convert to `InvalidValueError` / `PrecisionError`. | Before Step 5 (API input) |
| 3 | Minor | Provenance | A value calculated from an ESTIMATED input reads `calculated · verified`; the estimate is only visible through `leaves()`. | Add `rests_on_estimate`, spreading like SYNTHETIC. | Before Step 3 shows results |
| 4 | Minor | Property tests | Two properties recompute the implementation's own formula (`rate × kWh`, `kWh / kVAh`). | Use `fractions.Fraction` as an independent oracle. | Step 3 |
| 5 | Minor | Property tests | The rounding property cannot tell HALF_UP from HALF_EVEN and rarely generates exact .5 ties (covered only by example tables). | Add symmetry and monotonicity properties and a tie-forcing generator. | Step 3 |
| 6 | Minor | Provenance | With several MISSING inputs, the derived note names only the first. | List all missing inputs. | Step 3 |
| 7 | Minor | Public API | `Traced.missing()` returns `Traced[Any]`, losing the value type for mypy. | Optional type argument or typed overload. | Step 3 |
| 8 | Suggestion | Rounding | HALF_UP rounds ties away from zero (-12.5 → -13); some systems round towards +∞. | Confirm the convention for credits against the UP tariff order (24-row checklist). | Tariff verification |
| 9 | Suggestion | Units | `Energy / Duration → Power` (average demand) is valid but refused. | Add with explicit rounding when needed. | When needed |
| 10 | Suggestion | Money | `Rate` per kVA has no billing-period basis (per month vs per period). | Make the basis explicit in the tariff model. | Step 3 |
| 11 | Suggestion | Public API | Quantity's private `_value` can be reassigned (immutable by convention only). | Block `__setattr__` after `__init__`. | Step 3 |
| 12 | Suggestion | Public API | `Traced` accepts mutable or unhashable raw values; it is only shallowly frozen. | Document or check that raw values are immutable. | Step 3 |
| 13 | Suggestion | Provenance | `Traced.leaves()` is recursive (limit about 1,000 levels). | Iterative walk. | When needed |
| 14 | Suggestion | CI | GitHub Actions pinned to major tags, not commit SHAs. | Pin to SHAs. | Before freeze (1 Dec) |

Numbering follows the review document; #1 was the Major finding (fixed).
