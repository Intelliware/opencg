#!/usr/bin/env bash
# make demo-reset PACK=wealth|payments|retail|all
#
# Tombstones the pack's entities, and the concepts first seen in them, through the
# pipeline API as the opencg-demo-admin service account, so each tombstone is
# audited like any other. Re-running make demo-seed brings the entities back.
# The shared group documents are left alone.
set -euo pipefail
# shellcheck source=demo/scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_dev
PACK="${1:-${PACK:-all}}"
SELECTED=()
while IFS= read -r p; do SELECTED+=("$p"); done < <(packs_for "$PACK")

sql() {
  "${COMPOSE[@]}" exec -T postgres \
    sh -c 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "$1"' sh "$1" </dev/null
}

TOKEN="$(client_token opencg-demo-admin)"
HEADER_FILE="$(mktemp)"
trap 'rm -f "$HEADER_FILE"' EXIT
(umask 077 && printf 'authorization: Bearer %s\n' "$TOKEN" >"$HEADER_FILE")

delete_all() {
  local kind="$1" path="$2" ids="$3" n=0 id
  for id in $ids; do
    curl -fsS -o /dev/null -X DELETE -H @"$HEADER_FILE" "$PIPELINE_URL/$path/$id" || die "DELETE /$path/$id failed"
    n=$((n + 1))
  done
  say "$n $kind tombstoned"
}

for pack in "${SELECTED[@]}"; do
  like="git://opencg-demo-${pack}-%"
  entities="$(sql "SELECT entity_id FROM opencg.entity WHERE source_uri LIKE '$like' AND tombstoned_at IS NULL")"
  concepts="$(sql "SELECT c.concept_id FROM opencg.concept c JOIN opencg.entity e ON e.entity_id = c.source_entity_id
                   WHERE e.source_uri LIKE '$like' AND c.tombstoned_at IS NULL")"
  say "$pack:"
  delete_all concepts graph/concepts "$concepts"
  delete_all entities entities "$entities"
done
echo "✓ demo reset: ${SELECTED[*]} (run make demo-seed to restore)"
