#!/usr/bin/env bash
# make demo-seed PACK=wealth|payments|retail|all
#
# 1. Demo roles, personas and service accounts in the bundled Keycloak (idempotent).
# 2. Ingests demo/packs/group/internal once, then each pack's public, internal and
#    confidential folders as separate runs (confidential as confidential:<pack>).
# Runs only with OPENCG__ENVIRONMENT=dev. DEMO_STUB=1 uses the smoke chat stub.
set -euo pipefail
# shellcheck source=demo/scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_dev
PACK="${1:-${PACK:-all}}"
SELECTED=()
while IFS= read -r p; do SELECTED+=("$p"); done < <(packs_for "$PACK")

# --- Keycloak -----------------------------------------------------------------
role_rep() { kcadm get "roles/$1" -r opencg 2>/dev/null; }

ensure_roles() {
  local name description scope_id reps
  while IFS=$'\t' read -r name description; do
    if ! role_rep "$name" >/dev/null; then
      kcadm create roles -r opencg -s "name=$name" -s "description=$description" >/dev/null 2>&1
      say "role $name created"
    fi
  done < <(python3 -c 'import json,sys; [print(r["name"], r["description"], sep="\t") for r in json.load(open(sys.argv[1]))["roles"]]' "$DEMO/personas.json")
  # The opencg client scope only puts mapped roles into tokens (fullScopeAllowed is
  # off), so the demo roles must be added to its scope mappings.
  scope_id="$(kcadm get client-scopes -r opencg --fields id,name --format csv --noquotes | awk -F, '$2=="opencg"{print $1}')"
  [ -n "$scope_id" ] || die "client scope 'opencg' not found in the realm"
  reps="$(for r in wealth payments retail; do role_rep "$r"; done | python3 -c '
import json, sys
text, dec, out, i = sys.stdin.read(), json.JSONDecoder(), [], 0
while True:
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        break
    obj, i = dec.raw_decode(text, i)
    out.append(obj)
print(json.dumps(out))')"
  printf '%s' "$reps" | "${COMPOSE[@]}" exec -T keycloak sh -c 'cat >/tmp/demo-roles.json'
  kcadm create "client-scopes/$scope_id/scope-mappings/realm" -r opencg -f /tmp/demo-roles.json >/dev/null 2>&1 || true
}

user_id() { kcadm get users -r opencg -q "username=$1" -q exact=true --fields id --format csv --noquotes | head -n1; }

ensure_personas() {
  local password username first last roles id role
  password="$(cfg OPENCG__DEMO__PASSWORD "")"
  [ -n "$password" ] || die "OPENCG__DEMO__PASSWORD is not set (see .env.example)"
  while IFS=$'\t' read -r username first last roles; do
    id="$(user_id "$username")"
    if [ -z "$id" ]; then
      kcadm create users -r opencg -s "username=$username" -s enabled=true -s emailVerified=true \
        -s "email=$username@demo.invalid" -s "firstName=$first" -s "lastName=$last" >/dev/null
      say "persona $username created"
    fi
    printf '%s' "$password" | "${COMPOSE[@]}" exec -T keycloak sh -c 'cat >/tmp/demo-pw'
    "${COMPOSE[@]}" exec -T keycloak sh -c '
      /opt/keycloak/bin/kcadm.sh config credentials --config /tmp/kcadm.config --server http://localhost:8080 \
        --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null 2>&1
      /opt/keycloak/bin/kcadm.sh set-password --config /tmp/kcadm.config -r opencg --username "$1" --new-password "$(cat /tmp/demo-pw)"
      rm -f /tmp/demo-pw' sh "$username" </dev/null
    for role in $roles; do
      kcadm add-roles -r opencg --uusername "$username" --rolename "$role" >/dev/null
    done
  done < <(python3 -c 'import json,sys; [print(p["username"],p["first"],p["last"]," ".join(p["roles"]),sep="\t") for p in json.load(open(sys.argv[1]))["personas"]]' "$DEMO/personas.json")
}

ensure_service_accounts() {
  local client roles id role
  while IFS=$'\t' read -r client roles; do
    id="$(kcadm get clients -r opencg -q "clientId=$client" --fields id --format csv --noquotes | head -n1)"
    if [ -z "$id" ]; then
      kcadm create clients -r opencg -s "clientId=$client" -s enabled=true -s publicClient=false \
        -s serviceAccountsEnabled=true -s standardFlowEnabled=false -s directAccessGrantsEnabled=false \
        -s fullScopeAllowed=false -s 'description=openCG demo service account (dev only)' >/dev/null
      say "service account $client created"
    fi
    for role in $roles; do
      kcadm add-roles -r opencg --uusername "service-account-$client" --rolename "$role" >/dev/null
    done
  done < <(python3 -c 'import json,sys; [print(s["client_id"]," ".join(s["roles"]),sep="\t") for s in json.load(open(sys.argv[1]))["service_accounts"]]' "$DEMO/personas.json")
}

# --- Ingestion ----------------------------------------------------------------
INGEST_ENV=()
if [ "${DEMO_STUB:-0}" = "1" ]; then
  INGEST_ENV=(
    -e OPENCG__PROVIDERS__CHAT__BASE_URL=http://smoke-chat:11434
    -e OPENCG__PROVIDERS__CHAT__PROVIDER=ollama
    -e OPENCG__PROVIDERS__CHAT__MODEL=smoke-chat
    -e OPENCG__PROVIDERS__CHAT__API_KEY=
  )
elif [ -z "$(cfg OPENCG__PROVIDERS__CHAT__API_KEY "")" ]; then
  say "no OPENCG__PROVIDERS__CHAT__API_KEY: documents ingest and retrieval works, but the knowledge graph gets no extracted concepts"
fi

# ingest_folder PACK CLASS: copy the folder to /tmp, commit it, ingest it.
ingest_folder() {
  local pack="$1" class="$2" classification
  classification="$(classification_of "$pack" "$class")"
  "${COMPOSE[@]}" exec -T ingestion sh -c '
    set -eu
    src=/opt/opencg/demo-packs/$1/$2
    dst=/tmp/opencg-demo-$1-$2
    [ -d "$src" ] || { echo "missing $src" >&2; exit 1; }
    rm -rf "$dst" && cp -R "$src" "$dst"
    git -C "$dst" init -q
    git -C "$dst" config user.name "openCG Demo"
    git -C "$dst" config user.email "demo@localhost"
    git -C "$dst" add . && git -C "$dst" commit -qm "demo pack $1/$2"
  ' sh "$pack" "$class" </dev/null
  local log
  log="$(mktemp)"
  if ! "${COMPOSE[@]}" exec -T ${INGEST_ENV[@]+"${INGEST_ENV[@]}"} ingestion \
    uv run --package opencg-ingestion python -m opencg_ingestion.cli git "/tmp/opencg-demo-$pack-$class" \
    --classification "$classification" >"$log" 2>&1 </dev/null; then
    tail -n 30 "$log" >&2
    rm -f "$log"
    die "ingesting $pack/$class failed"
  fi
  rm -f "$log"
  say "ingested $pack/$class as $classification"
}

# OPA reads its data only at start; restart it so the demo domains are loaded.
"${COMPOSE[@]}" restart opa >/dev/null
say "OPA reloaded (demo confidential domains)"

say "Keycloak: demo roles, personas and service accounts"
ensure_roles
ensure_personas
ensure_service_accounts

# --- Optional per-persona dev API keys (DEMO_API_KEYS=1) -------------------------
# Raw keys go to demo/.persona-keys (mode 600, gitignored), never to the terminal;
# only their SHA-256 goes to demo/.api-keys.json, which pipeline and mcp-server load
# at start, so both are restarted.
ensure_api_keys() {
  python3 - "$DEMO/personas.json" "$DEMO/.api-keys.json" "$DEMO/.persona-keys" <<'PY'
import hashlib, json, os, secrets, sys
personas, hashes_path, raw_path = sys.argv[1:]
entries, lines = [], []
for p in json.load(open(personas))["personas"]:
    raw = "ock_" + secrets.token_urlsafe(32)
    entries.append({"name": f"demo-{p['username']}", "key_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "principal": p["username"], "roles": p["roles"]})
    lines.append(f"{p['username']}={raw}")
with open(hashes_path, "w") as f:  # rewrite in place: the bind mount follows the inode
    json.dump(entries, f, indent=2)
fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines) + "\n")
PY
  "${COMPOSE[@]}" restart pipeline mcp-server >/dev/null
  say "persona API keys written to demo/.persona-keys (dev only; pipeline and mcp-server restarted)"
}
if [ "${DEMO_API_KEYS:-0}" = "1" ]; then
  ensure_api_keys
fi

ingest_folder group internal
for pack in "${SELECTED[@]}"; do
  for class in "${CLASSES[@]}"; do
    ingest_folder "$pack" "$class"
  done
done

echo "✓ demo seeded: ${SELECTED[*]}. Sign in as demo-advisor, demo-payments-ops, demo-branch, demo-compliance or demo-reader (password: OPENCG__DEMO__PASSWORD in .env). See docs/DEMO.md."
