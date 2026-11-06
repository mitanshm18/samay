#!/usr/bin/env bash
# Start, stop or show SAMAY's own database (container samay-db). Step 4.
#
#   scripts/db.sh up      checks first, then starts samay-db and waits until healthy
#   scripts/db.sh down    stops and removes samay-db and samay_default; KEEPS the data
#                         volume samay_pgdata (never `down -v`)
#   scripts/db.sh status  read-only
#
# Every Docker command here goes through `docker compose` with this folder's
# compose.yaml, whose project name is "samay", so it can only address SAMAY's
# own resources (docs/docker-safety.md). Nothing is pulled, pruned or deleted.
# Written for macOS bash 3.2.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
MIN_FREE_GB=20

die() {
  echo "db: $*" >&2
  exit 1
}

compose() {
  docker compose --project-directory "$ROOT" -f "$ROOT/compose.yaml" --env-file "$ROOT/.env" "$@"
}

need_env() {
  [ -f .env ] || die ".env not found. Run: cp .env.example .env, then set SAMAY_PG_IMAGE and SAMAY_DB_PASSWORD"
}

scope_check() {
  compose config --format json | "$PYTHON" scripts/check_docker_scope.py \
    || die "Docker scope check failed; nothing was started or stopped"
}

disk_check() {
  local avail_kb free_gb
  avail_kb="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
  [ -n "$avail_kb" ] || die "could not read free disk space; not starting"
  free_gb=$((avail_kb / 1024 / 1024))
  if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
    die "only ${free_gb} GB free, below the ${MIN_FREE_GB} GB guardrail; not starting"
  fi
  echo "db: ${free_gb} GB free (guardrail ${MIN_FREE_GB} GB)"
}

image_check() {
  local image
  image="$(compose config --format json | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["services"]["db"]["image"])')"
  docker image inspect "$image" >/dev/null 2>&1 \
    || die "image $image is not on this machine. SAMAY never downloads images; set SAMAY_PG_IMAGE in .env to a tag from: docker image ls postgres"
}

# A samay-db / samay_pgdata / samay_default that SAMAY did not create is never touched.
owner_check() {
  local label
  if docker container inspect samay-db >/dev/null 2>&1; then
    label="$(docker container inspect --format '{{index .Config.Labels "org.samay.project"}}' samay-db)"
    [ "$label" = "samay" ] || die "a container named samay-db exists but is not SAMAY's; stopping"
  fi
  if docker volume inspect samay_pgdata >/dev/null 2>&1; then
    label="$(docker volume inspect --format '{{index .Labels "org.samay.project"}}' samay_pgdata)"
    [ "$label" = "samay" ] || die "a volume named samay_pgdata exists but is not SAMAY's; stopping"
  fi
  if docker network inspect samay_default >/dev/null 2>&1; then
    label="$(docker network inspect --format '{{index .Labels "com.docker.compose.project"}}' samay_default)"
    [ "$label" = "samay" ] || die "a network named samay_default exists but is not SAMAY's; stopping"
  fi
}

case "${1:-}" in
  up)
    need_env
    scope_check
    disk_check
    image_check
    owner_check
    compose up --detach --wait db  # pull_policy: never in compose.yaml
    compose ps db
    ;;
  down)
    need_env
    scope_check
    owner_check
    compose down
    echo "db: samay-db stopped; your saved data stays in volume samay_pgdata"
    ;;
  status)
    need_env
    compose ps --all db
    ;;
  *)
    die "usage: scripts/db.sh up|down|status"
    ;;
esac
