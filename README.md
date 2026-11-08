# SAMAY

Industrial electricity cost intelligence for Indian manufacturers.
Yuva Yodha Energy Tech Hackathon 2026, Challenge 04 (Smart Manufacturing). Team IdeaForge.

SAMAY processes structured factory electricity bill data, recomputes it from the tariff rules, reconciles every line with the printed bill, and shows illustrative what-if savings for the levers the bill reveals. Every number on screen comes from a real calculation, with its source and assumptions visible. Production-schedule optimisation (which batch timings would cost less) is planned for a later milestone and is not built yet.

> **Status:** Milestone 1, Step 7 (demo readiness) plus cost optimisation. Bills can be
> recalculated, reconciled with the printed bill, analysed for savings, saved and shown again, from the command line, the
> API ([docs/api.md](docs/api.md)) or a local web page ([frontend/README.md](frontend/README.md)).
> To run the demo, see [docs/demo.md](docs/demo.md).
> The tariff used in Milestone 1 is **SAMAY-DEMO-1 (SYNTHETIC — not UP rates)**.

## Team

| Role | Name |
| --- | --- |
| Team Leader | Mitansh Mathur |
| Team Member | Daksh Sehgal |

Team IdeaForge, IIIT Allahabad. Challenge 4 – Smart Manufacturing, Schneider Electric Yuva Yodha 2026.

## What is in the repository now

| Path | Purpose |
| --- | --- |
| `scripts/doctor.sh` | Read-only health check of your Mac and this project |
| `scripts/check_docker_scope.py` | Refuses any Docker setup that could touch non-SAMAY resources |
| `compose.yaml`, `scripts/db.sh` | SAMAY's own isolated PostgreSQL (`make db-up` / `make db-down`) |
| `docs/` | Architecture, Docker safety, data policy, storage, development guide, decisions |
| `backend/src/samay/core/` | Pure calculation core types (standard library only), fully tested |
| `backend/src/samay/tariffs/`, `billing/`, `io/`, `cli.py` | Tariff model, bill recalculation, reconciliation, JSON formats, `python -m samay.cli` |
| `backend/src/samay/db/`, `backend/migrations/` | Saved bills and reports in SAMAY's database, `python -m samay.db` |
| `backend/src/samay/api/` | Local HTTP API over the saved bills (`make api`) |
| `frontend/` | Local web page over the API: bill history, check a bill, line-by-line report, cost optimisation (`make web`) |

## Prerequisites

SAMAY is a local prototype. It runs on your own machine, at `127.0.0.1` only, and it is not deployed or production-ready. It has been developed on macOS and checked from a clean clone on Linux.

- **git**, **bash** and **make**. The Makefile is written for GNU make 3.81, which ships with macOS.
- **Python 3.13 or newer.** `backend/pyproject.toml` requires `>=3.13`. The Makefile sets `UV_PYTHON_DOWNLOADS=never`, so Python 3.13 must already be installed.
- **uv.** It installs the exact backend packages from `backend/uv.lock` into `backend/.venv`.
- **Node.js 22 or newer, and npm.** These are the versions CI uses. Frontend packages go into `frontend/node_modules`.
- **Docker with the Compose v2 plugin** (`docker compose`), and the **`postgres:16` image**. SAMAY never downloads images itself (`pull_policy: never`), so pull the image once with `docker pull postgres:16`.
- **At least 20 GB of free disk.** `make db-up` refuses to start below that.
- **Free local ports:** 55432 (database), 8000 (API) and 5173 (web page).

## Quick start (runs locally)

```bash
git clone https://github.com/mitanshm18/samay.git
cd samay
cp .env.example .env      # local settings: postgres:16 image, database port 55432
docker pull postgres:16   # once; SAMAY never downloads images itself
make db-up                # start SAMAY's own database on 127.0.0.1:55432
make db-migrate           # create its tables
make api                  # API on http://127.0.0.1:8000; leave it running
```

In a second terminal, from the same folder:

```bash
make web-install          # once: frontend packages
make web                  # then open http://127.0.0.1:5173
```

- **Optional, in a third terminal:**
  - `make demo-check` sends every sample bill through the running app. It saves one run per bill.
  - `make check` runs the tests (no Docker needed).
- **To stop:** press Ctrl-C in both terminals, then run `make db-down`. Saved data is kept.
- **Demo data:** all sample bills and the SAMAY-DEMO-1 tariff are synthetic, and the savings shown are illustrative. For the full walkthrough, see [docs/demo.md](docs/demo.md).

## First-time setup on a Mac (read-only)

These steps only create the project folder and copy files. Nothing is installed,
no Docker container is started, and other Docker projects are never touched.

```bash
mkdir -p ~/Developer
cd ~/Developer
git clone https://github.com/mitanshm18/samay.git
cd samay
cp .env.example .env
docker image ls postgres
```

Open `.env` and set `SAMAY_PG_IMAGE` to the exact `REPOSITORY:TAG` shown by the last
command (for example `postgres:16`). If no `postgres:16` image is listed, run
`docker pull postgres:16` once; SAMAY never downloads images itself. Then run the
read-only doctor:

```bash
make doctor
```

If `git clone` asks for a password, GitHub needs a personal access token instead;
see [docs/development.md](docs/development.md#cloning-a-private-repository).

## Commands

```bash
make help                 # list commands
make doctor               # read-only machine and project check
make check-docker-scope   # prove compose.yaml is isolated to SAMAY
make test-scripts         # run the helper-script tests
make backend-check        # backend: ruff, mypy --strict, tests with branch coverage
make check                # everything CI runs without Docker
make db-up                # start SAMAY's own database (see docs/docker-safety.md)
make db-migrate           # create or update its tables
make bill-save FILE=examples/bills/differing.json   # reconcile and save
make bill-history         # saved bills, newest first
make bill-show RUN=1      # a saved report exactly as produced
make api                  # local API on 127.0.0.1:8000 (docs/api.md)
make web-install          # once: frontend packages into frontend/node_modules
make web                  # web page on http://127.0.0.1:5173 (with make api running)
make demo-check           # every example bill through the running app
make db-down              # stop the database; saved data is kept
```

## Principles

- No fabricated data. Synthetic tariffs are labelled as synthetic everywhere.
- Deterministic calculations: money is held as integer paise, and every value carries
  its provenance (extracted, entered, calculated, estimated or missing).
- No fake functionality: a feature that is not built is not shown.
- Docker isolation: SAMAY only ever touches resources named `samay*`.
  See [docs/docker-safety.md](docs/docker-safety.md).

## Licence and use

Copyright © 2026 Team IdeaForge (Mitansh Mathur and Daksh Sehgal). All rights reserved.

This repository is proprietary. No licence is granted to use, copy, modify or
distribute this code. Access is provided only for evaluation in the Schneider Electric
Yuva Yodha 2026 hackathon. The libraries SAMAY depends on remain under their own
licences.
