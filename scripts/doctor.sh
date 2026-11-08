#!/usr/bin/env bash
# SAMAY doctor: READ-ONLY checks of this machine and this project.
#
# It never installs, creates, starts, stops or deletes anything, and never
# writes files. Docker is only queried (info, image inspect, ps, volume ls,
# compose config). Written for the bash 3.2 that ships with macOS.
#
# Usage:  scripts/doctor.sh          # full checks on a developer Mac
#         scripts/doctor.sh --ci     # CI runner: machine-specific checks are informational
#
# Exit status: 0 when there are no FAIL lines, 1 otherwise.

set -u

CI_MODE=0
if [ "${1:-}" = "--ci" ]; then
  CI_MODE=1
fi

MIN_FREE_GB=20      # hard stop agreed for SAMAY
WARN_FREE_GB=25
MIN_PYTHON="3.13"   # must match requires-python in backend/pyproject.toml
MIN_NODE="22"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

fails=0
warns=0

ok()   { printf '[ OK ] %s\n' "$1"; }
info() { printf '[INFO] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; warns=$((warns + 1)); }
fail() { printf '[FAIL] %s\n' "$1"; fails=$((fails + 1)); }
section() { printf '\n== %s ==\n' "$1"; }

# Soft failure: FAIL on a developer Mac, WARN on CI.
need() { if [ "$CI_MODE" -eq 1 ]; then warn "$1"; else fail "$1"; fi; }

have() { command -v "$1" >/dev/null 2>&1; }

# version_ge 3.13.9 3.12  -> true when the first version is >= the second
version_ge() {
  awk -v a="$1" -v b="$2" 'BEGIN {
    na = split(a, x, "."); nb = split(b, y, ".");
    n = (na > nb) ? na : nb;
    for (i = 1; i <= n; i++) {
      xi = (i <= na) ? x[i] + 0 : 0; yi = (i <= nb) ? y[i] + 0 : 0;
      if (xi > yi) exit 0; if (xi < yi) exit 1;
    }
    exit 0 }'
}

# Value of KEY from .env if present, otherwise from .env.example.
env_value() {
  local key="$1" file
  for file in .env .env.example; do
    if [ -f "$file" ]; then
      grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//'
      return
    fi
  done
}

printf 'SAMAY doctor (read-only)%s\n' "$( [ "$CI_MODE" -eq 1 ] && printf ' - CI mode' )"
printf 'Project folder: %s\n' "$ROOT"

# ---------------------------------------------------------------- location
section "Project location"
case "$ROOT" in
  *"Mobile Documents"*|*"CloudStorage"*)
    fail "Project is inside a cloud-synced folder; move it to ~/Developer/samay" ;;
  "$HOME/Developer/samay")
    ok "Project is at ~/Developer/samay" ;;
  *)
    if [ "$CI_MODE" -eq 1 ]; then info "Location check not applicable on CI"
    else warn "Project is not at the agreed location ~/Developer/samay"; fi ;;
esac

# ------------------------------------------------------------------- disk
section "Free disk space"
avail_kb="$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')"
if [ -z "$avail_kb" ]; then
  warn "Could not read free disk space"
else
  free_gb=$((avail_kb / 1024 / 1024))
  if [ "$CI_MODE" -eq 1 ]; then
    info "Free space on runner: ${free_gb} GB (guardrail applies to the developer Mac only)"
  elif [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
    fail "Only ${free_gb} GB free - below the ${MIN_FREE_GB} GB guardrail. Stop and free space before continuing."
  elif [ "$free_gb" -lt "$WARN_FREE_GB" ]; then
    warn "${free_gb} GB free - above the ${MIN_FREE_GB} GB guardrail but getting close"
  else
    ok "${free_gb} GB free (guardrail: stop below ${MIN_FREE_GB} GB)"
  fi
fi

# ------------------------------------------------------------------ tools
section "Tools"
if have git; then ok "git $(git --version | awk '{print $3}')"; else fail "git not found"; fi

if have python3; then
  py_ver="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
  # A FAIL on a developer Mac. On CI it is a WARN: the "checks" job uses the
  # runner's own python3 for the standard-library helper scripts only, while the
  # backend job installs Python 3.13 itself.
  if version_ge "$py_ver" "$MIN_PYTHON"; then ok "python3 $py_ver"
  else need "python3 $py_ver is older than $MIN_PYTHON (backend requires >=$MIN_PYTHON)"; fi
else
  fail "python3 not found"
fi

if have uv; then ok "uv $(uv --version | awk '{print $2}')"; else need "uv not found (needed from Step 2)"; fi

if have node; then
  node_ver="$(node -p 'process.versions.node')"
  if version_ge "$node_ver" "$MIN_NODE"; then ok "node $node_ver"
  else need "node $node_ver is older than $MIN_NODE"; fi
else
  need "node not found (needed from Step 6)"
fi
if have npm; then ok "npm $(npm --version)"; else need "npm not found (needed from Step 6)"; fi

# ----------------------------------------------------------------- docker
section "Docker (queried only, never changed)"
docker_up=0
have_compose=0
if ! have docker; then
  need "docker CLI not found"
else
  if compose_ver="$(docker compose version --short 2>/dev/null)"; then
    have_compose=1
    ok "Docker Compose $compose_ver"
  else
    need "docker compose plugin not available"
  fi
  if server_ver="$(docker info --format '{{.ServerVersion}}' 2>/dev/null)" && [ -n "$server_ver" ]; then
    docker_up=1
    ok "Docker engine $server_ver is running"
  else
    need "Docker is installed but not running (start Docker Desktop, then re-run)"
  fi
fi

# Rendering compose.yaml needs no running engine and starts nothing.
if [ "$have_compose" -eq 1 ]; then
  env_file=".env"
  [ -f "$env_file" ] || env_file=".env.example"
  if rendered="$(docker compose --env-file "$env_file" config --format json 2>/dev/null)"; then
    if scope_out="$(printf '%s' "$rendered" | python3 scripts/check_docker_scope.py)"; then
      ok "compose.yaml is isolated to project 'samay' (checked with $env_file)"
    else
      fail "compose.yaml failed the isolation check:"
      printf '%s\n' "$scope_out"
    fi
  else
    fail "compose.yaml could not be rendered with $env_file"
  fi
  unset rendered
fi

if [ "$docker_up" -eq 1 ]; then
  pg_image="$(env_value SAMAY_PG_IMAGE)"
  if [ "$CI_MODE" -eq 1 ]; then
    info "PostgreSQL image presence is checked on the developer Mac only"
  elif docker image inspect --format '{{.Id}}' "$pg_image" >/dev/null 2>&1; then
    ok "PostgreSQL image '$pg_image' is already present (nothing will be downloaded)"
  elif [ ! -f .env ]; then
    warn "Example image tag '$pg_image' is not on this Mac. In Step 4, set SAMAY_PG_IMAGE in .env to the tag shown by: docker image ls postgres"
  else
    fail "Image '$pg_image' from .env is not on this Mac; compose.yaml will refuse to download it. Check: docker image ls postgres"
  fi

  # Name collisions with resources SAMAY did not create.
  existing_label="$(docker container inspect --format '{{index .Config.Labels "org.samay.project"}}' samay-db 2>/dev/null || true)"
  if docker container inspect samay-db >/dev/null 2>&1; then
    if [ "$existing_label" = "samay" ]; then ok "Container samay-db exists and belongs to SAMAY"
    else fail "A container named samay-db exists but is not SAMAY's; do not start SAMAY until this is resolved"; fi
  else
    info "Container samay-db: not created yet (Step 4)"
  fi

  vol_label="$(docker volume inspect --format '{{index .Labels "org.samay.project"}}' samay_pgdata 2>/dev/null || true)"
  if docker volume inspect samay_pgdata >/dev/null 2>&1; then
    if [ "$vol_label" = "samay" ]; then ok "Volume samay_pgdata exists and belongs to SAMAY"
    else fail "A volume named samay_pgdata exists but is not SAMAY's; do not start SAMAY until this is resolved"; fi
  else
    info "Volume samay_pgdata: not created yet (Step 4)"
  fi

  other_count="$(docker ps -a -q 2>/dev/null | wc -l | tr -d ' ')"
  samay_count="$(docker ps -a -q --filter label=org.samay.project=samay 2>/dev/null | wc -l | tr -d ' ')"
  info "Containers on this machine: $other_count total, $samay_count belong to SAMAY. Others are never touched."
fi

# ------------------------------------------------------------------- port
section "Database port"
db_port="$(env_value SAMAY_DB_PORT)"
db_port="${db_port:-55432}"
if [ "$CI_MODE" -eq 1 ]; then
  info "Port check is for the developer Mac only"
elif ! have lsof; then
  warn "lsof not found; cannot check port $db_port"
elif listener="$(lsof -nP -iTCP:"$db_port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1" (pid "$2")"}')" && [ -n "$listener" ]; then
  if [ "$docker_up" -eq 1 ] && docker ps --filter name='^samay-db$' --filter status=running -q 2>/dev/null | grep -q .; then
    ok "Port $db_port is in use by SAMAY's own database"
  else
    fail "Port $db_port is already used by $listener; choose another SAMAY_DB_PORT in .env"
  fi
else
  ok "Port $db_port is free"
fi

# ---------------------------------------------------------- project files
section "Project files"
missing=0
for f in README.md Makefile compose.yaml .env.example .gitignore \
         scripts/check_docker_scope.py docs/architecture.md docs/docker-safety.md \
         docs/data-policy.md docs/development.md docs/storage.md; do
  if [ ! -f "$f" ]; then fail "Missing $f"; missing=1; fi
done
[ "$missing" -eq 0 ] && ok "All Step 1 files present"

if have git && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    fail ".env is tracked by git - it must never be committed"
  else
    ok ".env is not tracked by git"
  fi
  if git check-ignore -q .env; then ok ".env is git-ignored"; else fail ".env is not covered by .gitignore"; fi
fi

# ---------------------------------------------------------------- summary
printf '\n== Summary ==\n'
printf '%d failure(s), %d warning(s). The doctor made no changes.\n' "$fails" "$warns"
[ "$fails" -eq 0 ]
