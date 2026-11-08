# Development guide

## Requirements (already on the development Mac)

git, Python 3.13 or newer, uv, Node 22 or newer, npm, Docker Desktop
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
make backend-golden  # golden-bill merge gate: fails until the hand-check is signed off
make check           # everything above that needs no Docker
make bill-reconcile FILE=examples/bills/differing.json   # see cli.md
```

Database (Step 4, needs `.env` and Docker; see [docker-safety.md](docker-safety.md)):

```bash
make db-up            # start samay-db (checks scope, disk, image and ownership first)
make db-migrate       # apply migrations
make backend-db-test  # database and API tests in throwaway samay_test_* databases
make bill-save FILE=examples/bills/differing.json
make bill-history
make bill-show RUN=1      # exact saved report (python -m samay.db show 1 --source: the input)
make bill-verify RUN=1    # recalculate from the saved input and compare
make api              # local API on 127.0.0.1:8000, see api.md
```

Front end (Step 6, needs Node.js 20+ and npm; installs into `frontend/node_modules` only):

```bash
make web-install      # npm ci from frontend/package-lock.json (about 100 MB)
make web              # http://127.0.0.1:5173, with make api running in another terminal
make web-check        # type check, tests and production build (also in CI)
make demo-check       # every example bill through the running app (see demo.md)
make db-down          # stop; data in samay_pgdata is kept
```

The first `make backend-*` run after Step 4 also installs SQLAlchemy, Alembic and
psycopg into `backend/.venv` (about 20 MB).

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
| 2 | Core types: uv backend project, money in paise, explicit rounding, electricity units, meter intervals, provenance | Done (PR #2) |
| 3A | Tariff model, synthetic tariff SAMAY-DEMO-1, bill input, validation, `recompute_bill` | Done (PR #3) |
| 3B | `reconcile`, JSON command line, golden bills checked by hand | Done (PR #4) |
| 4 | Isolated database (`make db-up`), migrations, saved bills and reports | Done (PR #5) |
| 5 | Minimal local API ([api.md](api.md)) | Done (PR #6) |
| 6 | Demo front end ([frontend/README.md](../frontend/README.md)) | Done (PR #7) |
| 7 | End-to-end checks and demo readiness ([demo.md](demo.md)) | This step |

Step 2 was originally "Backend project with uv" and Step 3 "Calculation core".
They were re-scoped on 6 Nov 2026: Step 2 now includes the core types, and Step 3 is
the synthetic tariff with bill recomputation and reconciliation.

Step 3 was split into 3A and 3B on 6 Nov 2026 (decision 0003). 3B starts only after
3A is reviewed and merged, and 3B cannot merge until the golden bills are checked by hand.

Each step needs separate approval before it starts.
