# Docker safety

The Mac that runs SAMAY also runs other Docker projects (for example Pratikriti).
SAMAY must never modify, stop, delete, prune or rebuild anything it did not create.

## Rules

1. The Compose project name is always `samay`. Every `docker compose` command for SAMAY
   is run from this folder, so it can only address the `samay` project.
2. The container is `samay-db`; the volume is `samay_pgdata`; the network is `samay_default`.
   All carry the label `org.samay.project=samay`.
3. `pull_policy: never`: Docker never downloads an image for SAMAY. It reuses the
   PostgreSQL 16 image already on the Mac, named in `.env` as `SAMAY_PG_IMAGE`.
4. The database port is bound to `127.0.0.1` only (default 55432, not 5432).
5. No bind mounts, external volumes, external networks, `network_mode`, privileged mode,
   `pid`, `ipc`, `cap_add` or `devices`.
6. Never run, from any SAMAY script or instruction:
   `docker system prune`, `docker volume prune`, `docker image prune`, `docker network prune`,
   `docker rm`/`rmi` without an explicit `samay` name, or `docker compose down -v`
   outside this folder.

## How the rules are enforced

`scripts/check_docker_scope.py` reads the fully rendered Compose configuration
(`docker compose config --format json`) and fails if any rule above is broken.
It runs in CI on every push and in `make doctor` on the Mac. It has its own tests in
`scripts/tests/`.

```bash
make check-docker-scope
```

`scripts/doctor.sh` only queries Docker (`info`, `image inspect`, `container inspect`,
`volume inspect`, `ps`, `compose config`). It also checks that no container or volume
named `samay-db`/`samay_pgdata` exists that SAMAY did not create.

## Starting and stopping the database (Step 4)

```bash
make db-up       # start samay-db and wait until it is healthy
make db-migrate  # create or update SAMAY's tables
make db-status   # read-only
make db-down     # stop samay-db; the saved data in samay_pgdata is kept
```

`make db-up` runs `scripts/db.sh up`, which refuses to start unless, in order:

1. `.env` exists (copy `.env.example`, set `SAMAY_PG_IMAGE` and `SAMAY_DB_PASSWORD`);
2. the scope check above passes;
3. at least 20 GB is free (the storage guardrail);
4. the image named in `SAMAY_PG_IMAGE` is already on the machine (nothing is pulled);
5. any existing `samay-db`, `samay_pgdata` or `samay_default` belongs to SAMAY.

Only then does it run `docker compose up --detach --wait db` with this folder's
`compose.yaml`, which creates exactly `samay-db`, `samay_pgdata` and `samay_default`.
`make db-down` runs `docker compose down` **without** `-v`: the container and the
network go, the data volume stays. `scripts/tests/test_db_script.py` fails if the
script ever gains `prune`, `down -v`, `docker rm`/`rmi`/`pull`/`stop`, or a Compose
call that is not tied to this folder's `compose.yaml`.

Deleting SAMAY's saved data is deliberately not a Make target. If it is ever
needed, it is one explicit, named command: `docker volume rm samay_pgdata`
(after `make db-down`).

Database tests (`make backend-db-test`) create and drop their own
`samay_test_<random>` databases inside `samay-db`; the `samay` database is never
used by tests.
