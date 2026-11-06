# Development guide

## Requirements (already on the development Mac)

git, Python 3.12 or newer (3.13 in use), uv, Node 22 or newer, npm, Docker Desktop
with Compose, and the PostgreSQL 16 image. `make doctor` checks all of them without
changing anything.

## Cloning a private repository

The `gh` CLI is not needed. If `git clone https://github.com/mitanshm18/samay.git`
asks for a password:

1. On GitHub, open Settings, Developer settings, Personal access tokens,
   Fine-grained tokens, and create a token limited to the `samay` repository with
   **Contents: Read and write** and **Pull requests: Read**.
2. Tell git to store it in the macOS Keychain (one-time):
   ```bash
   git config --global credential.helper osxkeychain
   ```
3. Run the clone again. Username: `mitanshm18`. Password: paste the token.

## Daily commands

```bash
make doctor          # read-only check
make backend-check   # ruff, mypy --strict, tests with branch coverage
make check           # everything above that needs no Docker
```

The first `make backend-*` run creates `backend/.venv` (about 80-100 MB of development
tools: pytest, Hypothesis, coverage, ruff, mypy) from the exact versions in
`backend/uv.lock`. Nothing is installed globally and no Python is downloaded
(`UV_PYTHON_DOWNLOADS=never`). To remove it: `rm -rf backend/.venv`.

Known technical debt is tracked in [backlog.md](backlog.md).

Property tests use Hypothesis. `HYPOTHESIS_PROFILE=ci` (used in CI) is derandomised so runs
repeat exactly; `HYPOTHESIS_PROFILE=thorough` runs 5,000 examples per property.

## Branches and pull requests

- `main` is always working. All changes go through a pull request with green CI.
- Each Milestone 1 step is its own branch and pull request.
- Commit `.env` never. `make doctor` fails if it is tracked.

## Shell compatibility

Scripts must run on the macOS defaults: bash 3.2 and GNU make 3.81.
No associative arrays, `mapfile`, `${var,,}` or `.ONESHELL`.

## Milestone 1 steps

| Step | Scope | Status |
| --- | --- | --- |
| 1 | Skeleton, docs, Makefile, CI, read-only doctor | Done (PR #1) |
| 2 | Core types: uv backend project, money in paise, explicit rounding, electricity units, meter intervals, provenance | This step |
| 3 | Synthetic tariff SAMAY-DEMO-1, `recompute_bill`, `reconcile` | Not started |
| 4 | Isolated database (`make db-up`) and migrations | Not started |
| 5 | API | Not started |
| 6 | Front end | Not started |
| 7 | End-to-end vertical slice | Not started |

Step 2 was originally "Backend project with uv" and Step 3 "Calculation core".
They were re-scoped on 6 Nov 2026: Step 2 now includes the core types, and Step 3 is
the synthetic tariff with bill recomputation and reconciliation.

Each step needs separate approval before it starts.
