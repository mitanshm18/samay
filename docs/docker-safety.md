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

## Starting the database

Not in Step 1. Step 4 adds `make db-up` / `make db-down`, which will run the scope
check first and refuse to continue if it fails.
