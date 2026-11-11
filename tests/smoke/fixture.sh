#!/usr/bin/env bash
# CLI over the smoke fixture helpers, for callers outside run.sh (the admin UI
# Playwright global setup). Set OPENCG_E2E=1 to include the e2e overlay.
#
#   tests/smoke/fixture.sh up                       # apply the overlay(s) to a running stack
#   tests/smoke/fixture.sh restore                  # drop them again (ingestion back to .env settings)
#   tests/smoke/fixture.sh create RUN_ID [stub|cloud]
#   tests/smoke/fixture.sh ingest RUN_ID [stub|cloud]
#   tests/smoke/fixture.sh remove RUN_ID
#   tests/smoke/fixture.sh paths  RUN_ID            # prints dir=… and prefix=…
set -euo pipefail

# shellcheck source=tests/smoke/lib.sh
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

usage() {
  sed -n '2,10p' "$0" >&2
  exit 2
}

[ $# -ge 1 ] || usage
command="$1"
shift

case "$command" in
  up)
    services=(smoke-chat ingestion)
    if [ "${OPENCG_E2E:-0}" = "1" ]; then services+=(admin-ui-gated); fi
    "${COMPOSE[@]}" up -d --wait "${services[@]}"
    exit 0
    ;;
  restore)
    "${COMPOSE[@]}" rm -sf admin-ui-gated smoke-chat >/dev/null 2>&1 || true
    docker compose -f "$ROOT/infra/compose/docker-compose.yml" --env-file "$ROOT/.env" \
      --profile dev up -d --wait ingestion
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
