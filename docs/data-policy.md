# Data policy

## Nothing is invented

Every number SAMAY shows comes from a calculation over stated inputs. If an input is
unknown, it is shown as missing, not filled with a plausible guess.

## Provenance

Each value carries one of:

| Tag | Meaning |
| --- | --- |
| `extracted` | Read from a document (bill, tariff order), with page reference |
| `entered` | Typed in by the user |
| `calculated` | Produced by SAMAY's calculation core from other values |
| `estimated` | An explicit assumption, shown with its basis |
| `missing` | Not available; results that depend on it say so |

In code these are `samay.core.Provenance` values carried by `samay.core.Traced`.
Every value also has a separate **data status**, `SYNTHETIC` or `VERIFIED`
(`samay.core.DataStatus`): anything derived from a synthetic input is synthetic, and
nothing can turn it back into verified.

## Tariffs: synthetic vs verified

- **Synthetic** tariffs exist to build and test the software. They are named with
  `SYNTHETIC` and the words "not UP rates", and every screen and report that uses one
  says so.
- **Verified** tariffs come from a published tariff order. Each rule records the page and
  clause, the interpretation, the unit, and an example checked independently by a person.
  The UP HV-2 tariff is added only after its 24-row checklist is complete.

## Real data

Real bills or factory data never go into git. Keep them in `private-data/`
(git-ignored). Generated and downloaded data go in `data/public/` and `data/synthetic/`,
which are also git-ignored.
