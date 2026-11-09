# Shared helpers for tests/smoke/run.sh and tests/smoke/fixture.sh. Source it;
# don't execute it. Sets ROOT and COMPOSE.
#
# Set OPENCG_E2E=1 to add the e2e overlay on top of the smoke overlay (see
# infra/compose/docker-compose.e2e.yml). OPENCG_ROOT points the helpers at
# another checkout's compose files and .env.

ROOT="${OPENCG_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Read a setting from the environment, else from $ROOT/.env, else a default.
# Keeps host ports in step with the compose file's OPENCG__*__HOST_PORT values.
cfg() {
  local key="$1" default="$2" value="${!1:-}"
  if [ -z "$value" ] && [ -f "$ROOT/.env" ]; then
    value="$(sed -n "s/^${key}=//p" "$ROOT/.env" | tail -n 1)"
  fi
  printf '%s' "${value:-$default}"
}

# The smoke overlay adds the chat stub and mounts the fixture into ingestion;
# it is never part of the default `make up-d` stack.
COMPOSE=(
  docker compose
  -f "$ROOT/infra/compose/docker-compose.yml"
  -f "$ROOT/infra/compose/docker-compose.smoke.yml"
)
if [ "${OPENCG_E2E:-0}" = "1" ]; then
  COMPOSE+=(-f "$ROOT/infra/compose/docker-compose.e2e.yml")
fi
COMPOSE+=(--env-file "$ROOT/.env" --profile dev)

# A fixture named after RUN_ID lives at /tmp/opencg-smoke-<RUN_ID> inside the
# ingestion container, and every entity it produces has this source_uri prefix.
fixture_dir() { printf '/tmp/opencg-smoke-%s' "$1"; }
fixture_prefix() { printf 'git://opencg-smoke-%s/' "$1"; }

# fixture_create RUN_ID [stub|cloud]: copy the committed fixture, stamp the run
# ID into it (the chat stub derives run-unique concept names from it) and commit.
fixture_create() {
  local run_id="$1" mode="${2:-stub}"
  "${COMPOSE[@]}" exec -T ingestion sh -c '
    set -eu
    destination=$1
    run_id=$2
    rm -rf "$destination"
    cp -R /opt/opencg/smoke-fixture "$destination"
    sed -i "s/SMOKE_RUN_ID/$run_id/g" "$destination/README.md"
    if [ "$3" = "cloud" ]; then
      rm -f "$destination/context_tools.py"
    fi
    git -C "$destination" init -q
    git -C "$destination" config user.name "openCG Smoke"
    git -C "$destination" config user.email "smoke@localhost"
    git -C "$destination" add .
    git -C "$destination" commit -qm "smoke fixture"
  ' sh "$(fixture_dir "$run_id")" "$run_id" "$mode"
}

# fixture_ingest RUN_ID [stub|cloud]: ingest the fixture with the CLI. Stub mode
# points extraction at the compose-internal chat stub; cloud mode uses the
# ingestion container's configured provider with tighter bounds.
fixture_ingest() {
  local run_id="$1" mode="${2:-stub}"
  local args=(exec -T)
  local max_documents max_chunks
  if [ "$mode" = "stub" ]; then
    args+=(
      -e OPENCG__PROVIDERS__CHAT__BASE_URL=http://smoke-chat:11434
      -e OPENCG__PROVIDERS__CHAT__MODEL=smoke-chat
      -e OPENCG__PROVIDERS__CHAT__API_KEY=
    )
    max_documents=10
    max_chunks=20
  else
    max_documents=1
    max_chunks=2
  fi
  "${COMPOSE[@]}" "${args[@]}" ingestion \
    uv run --package opencg-ingestion \
    python -m opencg_ingestion.cli git "$(fixture_dir "$run_id")" \
    --max-documents "$max_documents" \
    --max-chunks "$max_chunks"
}

# fixture_remove RUN_ID: delete the fixture copy (catalogue rows stay; every
# assertion is scoped to the run's source_uri prefix).
fixture_remove() {
  "${COMPOSE[@]}" exec -T ingestion rm -rf "$(fixture_dir "$1")" >/dev/null 2>&1 || true
}
