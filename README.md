# SAMAY

Industrial electricity cost intelligence for Indian manufacturers.
Yuva Yodha Energy Tech Hackathon 2026, Challenge 04 (Smart Manufacturing). Team IdeaForge.

SAMAY reads a factory's electricity bill and production schedule, recomputes the bill
from the tariff rules, explains every rupee, and shows which batch timings would cost less.
Every number on screen comes from a real calculation, with its source and assumptions visible.

> **Status:** Milestone 1, Step 1 (project skeleton). There is no application code yet.
> The tariff used in Milestone 1 is **SAMAY-DEMO-1 (SYNTHETIC — not UP rates)**.

## What is in the repository now

| Path | Purpose |
| --- | --- |
| `scripts/doctor.sh` | Read-only health check of your Mac and this project |
| `scripts/check_docker_scope.py` | Refuses any Docker setup that could touch non-SAMAY resources |
| `compose.yaml` | SAMAY's own isolated PostgreSQL (not started until Step 4) |
| `docs/` | Architecture, Docker safety, data policy, storage, development guide, decisions |
| `backend/`, `frontend/` | Placeholders; code arrives in Steps 2 and 6 |

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
command (for example `postgres:16`). Then run the read-only doctor:

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
make check                # tests + shell checks (what CI runs without Docker)
```

## Principles

- No fabricated data. Synthetic tariffs are labelled as synthetic everywhere.
- Deterministic calculations: money is held as integer paise, and every value carries
  its provenance (extracted, entered, calculated, estimated or missing).
- No fake functionality: a feature that is not built is not shown.
- Docker isolation: SAMAY only ever touches resources named `samay*`.
  See [docs/docker-safety.md](docs/docker-safety.md).
