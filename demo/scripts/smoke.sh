#!/usr/bin/env bash
# make demo-smoke: seed every pack with the smoke chat stub, check each
# (pack, classification) ingested, check the split answer for every scripted
# question (domain persona sees the confidential document; demo-reader doesn't,
# and gets the internal referral), then reset. Runs in the CI stack job.
set -euo pipefail
export DEMO_STUB=1
# shellcheck source=demo/scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_dev
say "Applying the demo overlay"
"${COMPOSE[@]}" up -d --wait smoke-chat ingestion pipeline keycloak >/dev/null

"$DEMO/scripts/seed.sh" all

sql() {
  "${COMPOSE[@]}" exec -T postgres \
    sh -c 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "$1"' sh "$1" </dev/null
}

failures=0
fail() { echo "✗ $*" >&2; failures=$((failures + 1)); }

say "Every pack folder ingested with its classification"
for pack in "${PACKS[@]}"; do
  for class in "${CLASSES[@]}"; do
    want="$(classification_of "$pack" "$class")"
    files="$(find "$DEMO/packs/$pack/$class" -name '*.md' | wc -l | tr -d ' ')"
    got="$(sql "SELECT count(DISTINCT split_part(source_uri, '#', 1)) FROM opencg.entity
                WHERE source_uri LIKE '$(prefix_of "$pack" "$class")%' AND tombstoned_at IS NULL
                  AND classification = '$want'")"
    [ "$got" -ge "$files" ] || fail "$pack/$class: $got document(s) classified $want, want $files"
  done
done

say "Split answers per persona"
TOKENS_DIR="$(mktemp -d)"
trap 'rm -rf "$TOKENS_DIR"' EXIT
for client in opencg-demo-reader opencg-demo-advisor opencg-demo-payments-ops opencg-demo-branch; do
  (umask 077 && printf 'authorization: Bearer %s\n' "$(client_token "$client")" >"$TOKENS_DIR/$client")
done

retrieve_as() { # CLIENT QUERY -> JSON
  python3 -c 'import json,sys; print(json.dumps({"correlation_id": sys.argv[2], "tool": "retrieve_for_context",
    "identity": {"principal": "demo-smoke", "roles": ["reader"], "tenant": "default"},
    "query": sys.argv[1], "top_k": 10, "token_budget": 4000}))' "$2" "demo-smoke-$1-$RANDOM" |
    curl -fsS -X POST "$PIPELINE_URL/retrieve" -H @"$TOKENS_DIR/$1" -H 'content-type: application/json' -d @-
}

for pack in "${PACKS[@]}"; do
  while IFS=$'\t' read -r id persona question internal confidential; do
    conf_uri="$(prefix_of "$pack" confidential)${confidential#confidential/}"
    int_uri="$(prefix_of "$pack" internal)${internal#internal/}"
    persona_json="$(retrieve_as "opencg-$persona" "$question")" || { fail "$id: retrieve as $persona failed"; continue; }
    reader_json="$(retrieve_as opencg-demo-reader "$question")" || { fail "$id: retrieve as demo-reader failed"; continue; }
    python3 - "$id" "$persona" "$conf_uri" "$int_uri" "$persona_json" "$reader_json" <<'PY' || failures=$((failures + 1))
import json, sys
qid, persona, conf, internal, persona_json, reader_json = sys.argv[1:]
def uris(raw): return [f["source_uri"] for f in json.loads(raw)["fragments"]]
p, r = uris(persona_json), uris(reader_json)
problems = []
if not any(u.startswith(conf) for u in p):
    problems.append(f"{persona} did not get {conf}")
leaked = [u for u in r if "-confidential/" in u]
if leaked:
    problems.append(f"demo-reader got confidential fragment(s) {leaked[:2]}")
if not any(u.startswith(internal) for u in r):
    problems.append(f"demo-reader did not get the referral {internal}")
for msg in problems:
    print(f"✗ {qid}: {msg}", file=sys.stderr)
sys.exit(1 if problems else 0)
PY
  done < <(python3 -c 'import json,sys; [print(q["id"],q["persona"],q["question"],q["internal"],q["confidential"],sep="\t") for q in json.load(open(sys.argv[1]))]' "$DEMO/packs/$pack/questions.json")
done

"$DEMO/scripts/reset.sh" all
[ "$failures" -eq 0 ] || die "demo smoke: $failures failure(s)"
echo "✓ demo smoke passed"
