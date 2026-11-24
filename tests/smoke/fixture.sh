#!/usr/bin/env bash
# CLI over the smoke fixture helpers, for callers outside run.sh (the admin UI
# Playwright global setup). Set OPENCG_E2E=1 to include the e2e overlay;
# OPENCG_TEST_AUTH_MODE (default oidc) picks the auth overlay (see lib.sh).
#
#   tests/smoke/fixture.sh up                       # apply the overlay(s) to a running stack
#   tests/smoke/fixture.sh restore                  # drop them again (services back to .env settings)
#   tests/smoke/fixture.sh sql QUERY                # run a query in Postgres, print rows (tA, "|")
#   tests/smoke/fixture.sh create RUN_ID [stub|cloud]
#   tests/smoke/fixture.sh ingest RUN_ID [stub|cloud]
#   tests/smoke/fixture.sh remove RUN_ID
#   tests/smoke/fixture.sh paths  RUN_ID            # prints dir=… and prefix=…
set -euo pipefail

# shellcheck source=tests/smoke/lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

usage() {
  sed -n '2,12p' "$0" >&2
  exit 2
}

[ $# -ge 1 ] || usage
command="$1"
shift

case "$command" in
  up)
    "${COMPOSE[@]}" up -d --wait "${OVERLAY_SERVICES[@]}"
    exit 0
    ;;
  restore)
    "${COMPOSE[@]}" rm -sf smoke-chat >/dev/null 2>&1 || true
    # Back to what .env says: drop the forced test mode, recreate the services
    # whose settings the overlays changed, and stop the bundled Keycloak unless
    # .env itself runs oidc.
    env -u OPENCG__AUTH__MODE docker compose -f "$ROOT/infra/compose/docker-compose.yml" \
      --env-file "$ROOT/.env" --profile dev up -d --wait pipeline ingestion mcp-server admin-ui
    if [ "$(OPENCG__AUTH__MODE='' cfg OPENCG__AUTH__MODE none)" != "oidc" ]; then
      docker compose -f "$ROOT/infra/compose/docker-compose.yml" --env-file "$ROOT/.env" \
        --profile dev --profile idp rm -sf keycloak >/dev/null 2>&1 || true
    fi
    exit 0
    ;;
  sql)
    [ $# -eq 1 ] || usage
    "${COMPOSE[@]}" exec -T postgres \
      sh -c 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -F "|" -c "$1"' sh "$1" \
      | tr -d '\r'
    exit 0
    ;;
esac

[ $# -ge 1 ] || usage
run_id="$1" mode="${2:-stub}"
[[ "$run_id" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "RUN_ID must match [A-Za-z0-9_-]+" >&2; exit 2; }
case "$mode" in stub | cloud) ;; *) usage ;; esac

case "$command" in
  create) fixture_create "$run_id" "$mode" ;;
  ingest) fixture_ingest "$run_id" "$mode" ;;
  remove) fixture_remove "$run_id" ;;
  paths) printf 'dir=%s\nprefix=%s\n' "$(fixture_dir "$run_id")" "$(fixture_prefix "$run_id")" ;;
  *) usage ;;
esac
