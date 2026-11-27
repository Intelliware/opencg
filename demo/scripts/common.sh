#!/usr/bin/env bash
# Shared helpers for demo/scripts/{seed,reset,smoke}.sh (add-showcase-seed-packs).
# Sourced, not run. Never prints secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO="$ROOT/demo"
PACKS=(wealth payments retail)
CLASSES=(public internal confidential)

# cfg KEY DEFAULT: the shell value, else the last KEY= line in .env, else DEFAULT.
cfg() {
  local key="$1" default="$2" value="${!1:-}"
  if [ -z "$value" ] && [ -f "$ROOT/.env" ]; then
    value="$(sed -n "s/^${key}=//p" "$ROOT/.env" | tail -n 1)"
  fi
  printf '%s' "${value:-$default}"
}

# The demo stack: base + oidc overlay (bundled Keycloak) + demo overlay. DEMO_STUB=1
# (demo-smoke) adds the smoke overlay for its deterministic chat stub.
COMPOSE=(
  docker compose
  -f "$ROOT/infra/compose/docker-compose.yml"
  -f "$ROOT/infra/compose/docker-compose.oidc.yml"
  -f "$ROOT/infra/compose/docker-compose.demo.yml"
)
if [ "${DEMO_STUB:-0}" = "1" ]; then
  COMPOSE+=(-f "$ROOT/infra/compose/docker-compose.smoke.yml")
fi
# Keep the observability overlay if the demo was started with `make demo-up OBS=1`,
# so later compose calls don't recreate services without it.
if [ -n "$(docker ps -q --filter label=com.docker.compose.service=grafana 2>/dev/null)" ]; then
  COMPOSE+=(-f "$ROOT/infra/compose/docker-compose.observability.yml")
fi
COMPOSE+=(--env-file "$ROOT/.env" --profile dev --profile idp)

# The demo overlay mounts this file into pipeline and mcp-server; it must exist.
[ -f "$DEMO/.api-keys.json" ] || printf '[]\n' >"$DEMO/.api-keys.json"

OIDC_ISSUER="$(cfg OPENCG__KEYCLOAK__PUBLIC_URL "http://localhost:$(cfg OPENCG__KEYCLOAK__HOST_PORT 8380)")/realms/opencg"
PIPELINE_URL="http://localhost:$(cfg OPENCG__PIPELINE__HOST_PORT 8000)"

die() { echo "✗ $*" >&2; exit 1; }
say() { echo "• $*"; }

require_dev() {
  local env
  env="$(cfg OPENCG__ENVIRONMENT production)"
  [ "$env" = "dev" ] || die "demo tooling runs only with OPENCG__ENVIRONMENT=dev (got '$env')"
}

# packs_for ARG: expand wealth|payments|retail|all to pack names.
packs_for() {
  case "${1:-all}" in
    all) printf '%s\n' "${PACKS[@]}" ;;
    wealth | payments | retail) printf '%s\n' "$1" ;;
    *) die "PACK must be wealth, payments, retail or all (got '$1')" ;;
  esac
}

# classification_of PACK CLASS
classification_of() {
  if [ "$2" = "confidential" ]; then printf 'confidential:%s' "$1"; else printf '%s' "$2"; fi
}

# prefix_of PACK CLASS: the source URI prefix of every entity from that folder.
prefix_of() { printf 'git://opencg-demo-%s-%s/' "$1" "$2"; }

# kcadm ARGS...: Keycloak admin CLI inside the keycloak container, logged in with
# the bootstrap admin from the container's own environment (never on our command line).
kcadm() {
  "${COMPOSE[@]}" exec -T keycloak sh -c '
    /opt/keycloak/bin/kcadm.sh config credentials --config /tmp/kcadm.config \
      --server http://localhost:8080 --realm master \
      --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null 2>&1
    exec /opt/keycloak/bin/kcadm.sh "$@" --config /tmp/kcadm.config
  ' kcadm "$@" </dev/null
}

# client_token CLIENT_ID: a client-credentials access token for a demo service
# account. The secret is read through kcadm and never printed.
client_token() {
  local client="$1" id secret
  id="$(kcadm get clients -r opencg -q "clientId=$client" --fields id --format csv --noquotes | head -n1)"
  [ -n "$id" ] || die "no Keycloak client $client; run make demo-seed first"
  secret="$(kcadm get "clients/$id/client-secret" -r opencg --fields value --format csv --noquotes)"
  curl -fsS --max-time 15 -X POST "$OIDC_ISSUER/protocol/openid-connect/token" \
    --data-urlencode grant_type=client_credentials \
    --data-urlencode "client_id=$client" \
    --data-urlencode "client_secret=$secret" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}
