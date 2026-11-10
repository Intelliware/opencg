#!/usr/bin/env bash
# Deterministic end-to-end verification for an already-built healthy dev stack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=tests/smoke/lib.sh
source "$ROOT/tests/smoke/lib.sh"

PIPELINE_URL="${PIPELINE_URL:-http://localhost:$(cfg OPENCG__PIPELINE__HOST_PORT 8000)}"
QDRANT_URL="${QDRANT_URL:-http://localhost:$(cfg OPENCG__QDRANT__HOST_PORT 6333)}"
SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-300}"
SMOKE_INGEST_TIMEOUT_SECONDS="${SMOKE_INGEST_TIMEOUT_SECONDS:-120}"
SMOKE_CHAT_MODE="${SMOKE_CHAT_MODE:-stub}"
RUN_ID="$(date -u +%Y%m%d%H%M%S)-$$"
FIXTURE_DIR="$(fixture_dir "$RUN_ID")"
SOURCE_PREFIX="$(fixture_prefix "$RUN_ID")"
START_SECONDS=$SECONDS
SMOKE_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ACTIVE_PID=""
OVERALL_TIMER=""
STAGE_LOG=""

say() { printf '\n\e[1;36m▌ %s\e[0m\n' "$*"; }
pass() { printf '✓ %s\n' "$*"; }
fail() { printf '✗ %s\n' "$*" >&2; exit 1; }

if [ "${SMOKE_DRY_RUN:-0}" = "1" ]; then
  case "$SMOKE_CHAT_MODE" in
    stub)
      printf 'mode=stub external_chat=false max_documents=10 max_chunks=20 timeout=%s\n' \
        "$SMOKE_TIMEOUT_SECONDS"
      ;;
    cloud)
      printf 'mode=cloud external_chat=true max_documents=1 max_chunks=2 timeout=%s\n' \
        "$SMOKE_TIMEOUT_SECONDS"
      ;;
    *)
      fail "SMOKE_CHAT_MODE must be 'stub' or 'cloud'"
      ;;
  esac
  exit 0
fi
case "$SMOKE_CHAT_MODE" in
  stub | cloud) ;;
  *) fail "SMOKE_CHAT_MODE must be 'stub' or 'cloud'" ;;
esac

kill_ingestion_children() {
  "${COMPOSE[@]}" exec -T ingestion sh -c '
    for proc in /proc/[0-9]*; do
      cmd=$(tr "\0" " " < "$proc/cmdline" 2>/dev/null || true)
      case "$cmd" in
        *"opencg_ingestion.cli git"*) kill "${proc##*/}" 2>/dev/null || true ;;
      esac
    done
  ' >/dev/null 2>&1 || true
}

cleanup() {
  local status=$?
  if [ -n "$ACTIVE_PID" ]; then
    kill "$ACTIVE_PID" >/dev/null 2>&1 || true
  fi
  kill_ingestion_children
  fixture_remove "$RUN_ID"
  if [ -n "$OVERALL_TIMER" ]; then
    kill "$OVERALL_TIMER" >/dev/null 2>&1 || true
  fi
  if [ -n "$STAGE_LOG" ]; then
    rm -f "$STAGE_LOG"
  fi
  return "$status"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

(
  sleep "$SMOKE_TIMEOUT_SECONDS"
  printf '\n✗ full smoke exceeded %ss overall deadline\n' "$SMOKE_TIMEOUT_SECONDS" >&2
  kill -TERM "$$"
) &
OVERALL_TIMER=$!

run_timed() {
  local name=$1
  local timeout=$2
  shift 2
  local started=$SECONDS
  local timer
  STAGE_LOG="$(mktemp)"
  say "$name"
  "$@" >"$STAGE_LOG" 2>&1 &
  ACTIVE_PID=$!
  (
    sleep "$timeout"
    kill -TERM "$ACTIVE_PID" >/dev/null 2>&1 || true
  ) &
  timer=$!
  local status
  if wait "$ACTIVE_PID"; then
    kill "$timer" >/dev/null 2>&1 || true
    wait "$timer" 2>/dev/null || true
    ACTIVE_PID=""
    cat "$STAGE_LOG"
    pass "$name completed in $((SECONDS - started))s"
    return 0
  else
    status=$?
  fi
  kill "$timer" >/dev/null 2>&1 || true
  wait "$timer" 2>/dev/null || true
  ACTIVE_PID=""
  cat "$STAGE_LOG" >&2
  fail "$name failed after $((SECONDS - started))s (exit $status)"
}

psql_value() {
  # Credentials come from the container's own POSTGRES_* environment.
  "${COMPOSE[@]}" exec -T postgres \
    sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -F "|" -c "$1"' sh "$1" \
    | tr -d '\r'
}

say "Apply the smoke overlay (chat stub + fixture mount)"
"${COMPOSE[@]}" up -d --wait smoke-chat ingestion

say "Wait for pipeline and smoke dependencies"
for _ in $(seq 1 60); do
  STUB_READY=true
  if [ "$SMOKE_CHAT_MODE" = "stub" ]; then
    "${COMPOSE[@]}" exec -T smoke-chat \
      python -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/healthz')" \
      >/dev/null 2>&1 || STUB_READY=false
  fi
  if curl -fsS "$PIPELINE_URL/readyz" >/dev/null 2>&1 && [ "$STUB_READY" = true ]; then
    break
  fi
  sleep 2
done
curl -fsS "$PIPELINE_URL/readyz"
if [ "$SMOKE_CHAT_MODE" = "stub" ]; then
  "${COMPOSE[@]}" exec -T smoke-chat \
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/healthz')" \
    >/dev/null
fi
pass "pipeline and smoke dependencies are ready"

say "Verify Qdrant client/server compatibility"
CLIENT_VERSION="$("${COMPOSE[@]}" exec -T ingestion uv run python -c \
  "import importlib.metadata; print(importlib.metadata.version('qdrant-client'))")"
SERVER_VERSION="$(curl -fsS "$QDRANT_URL/" | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["version"])')"
python3 - "$CLIENT_VERSION" "$SERVER_VERSION" <<'PY'
import sys

client, server = sys.argv[1:3]
if client.split(".")[:2] != server.split(".")[:2]:
    raise SystemExit(
        f"Qdrant version mismatch: client={client}, server={server}; "
        "major/minor versions must match"
    )
PY
pass "Qdrant client $CLIENT_VERSION matches server $SERVER_VERSION"

say "Construct isolated local Git fixture"
fixture_create "$RUN_ID" "$SMOKE_CHAT_MODE"
pass "fixture ready at $FIXTURE_DIR with source prefix $SOURCE_PREFIX"

if [ "$SMOKE_CHAT_MODE" = "cloud" ]; then
  "${COMPOSE[@]}" exec -T ingestion sh -c '
    test -n "${OPENCG__PROVIDERS__CHAT__BASE_URL:-}" &&
    test -n "${OPENCG__PROVIDERS__CHAT__MODEL:-}" &&
    test -n "${OPENCG__PROVIDERS__CHAT__API_KEY:-}"
  ' || fail "cloud mode requires chat base URL, model, and OPENCG__PROVIDERS__CHAT__API_KEY"
fi

run_timed "Ingest deterministic fixture ($SMOKE_CHAT_MODE chat)" \
  "$SMOKE_INGEST_TIMEOUT_SECONDS" fixture_ingest "$RUN_ID" "$SMOKE_CHAT_MODE"
INGEST_OUTPUT="$(cat "$STAGE_LOG")"
PARENTS="$(printf '%s' "$INGEST_OUTPUT" | sed -n 's/.*Ingested \([0-9][0-9]*\) files.*/\1/p' | tail -1)"
CHUNKS="$(printf '%s' "$INGEST_OUTPUT" | sed -n 's/.*files \/ \([0-9][0-9]*\) chunks.*/\1/p' | tail -1)"
[ -n "$PARENTS" ] && [ -n "$CHUNKS" ] || fail "could not parse ingestion summary"
[ "$CHUNKS" -gt 0 ] && [ "$CHUNKS" -lt 20 ] || fail "fixture produced $CHUNKS chunks; expected 1..19"
if [ "$SMOKE_CHAT_MODE" = "cloud" ]; then
  [ "$PARENTS" -le 1 ] && [ "$CHUNKS" -le 2 ] || fail "cloud canary exceeded bounds"
else
  STUB_REQUESTS="$("${COMPOSE[@]}" exec -T smoke-chat python -c \
    "import json,urllib.request; print(json.load(urllib.request.urlopen('http://localhost:11434/stats'))['chat_requests'])")"
  [ "$STUB_REQUESTS" -ge 1 ] || fail "deterministic chat stub received no requests"
fi
pass "fixture ingested: parents=$PARENTS chunks=$CHUNKS"

if [ "$SMOKE_CHAT_MODE" = "cloud" ]; then
  say "Verify bounded cloud extraction"
  CLOUD_EDGE_COUNT="$(psql_value "
    SELECT count(*)
    FROM opencg.relationship_edge edge
    JOIN opencg.relationship_evidence evidence ON evidence.edge_id = edge.edge_id
    JOIN opencg.entity entity ON entity.entity_id = evidence.entity_id
    WHERE entity.source_uri LIKE '${SOURCE_PREFIX}%'
      AND edge.extractor_version LIKE 'text-extractor/%'
  ")"
  [ "${CLOUD_EDGE_COUNT:-0}" -ge 1 ] || fail "cloud response produced no parseable relationship"

  FOUND_CLOUD_SPAN=false
  for _ in $(seq 1 20); do
    OTEL_LOGS="$("${COMPOSE[@]}" logs --since "$SMOKE_STARTED_AT" otel-collector 2>&1 || true)"
    if grep -q 'pipeline.graph_extract_text' <<<"$OTEL_LOGS" \
      && grep -Eq 'tokens_in.*Int\([1-9][0-9]*\)' <<<"$OTEL_LOGS" \
      && grep -Eq 'tokens_out.*Int\([1-9][0-9]*\)' <<<"$OTEL_LOGS"; then
      FOUND_CLOUD_SPAN=true
      break
    fi
    sleep 1
  done
  [ "$FOUND_CLOUD_SPAN" = true ] || fail "cloud extraction span lacked non-zero token attributes"
  TOTAL_SECONDS=$((SECONDS - START_SECONDS))
  say "Cloud canary PASSED"
  printf 'run_id=%s mode=cloud parents=%s chunks=%s edges=%s duration=%ss\n' \
    "$RUN_ID" "$PARENTS" "$CHUNKS" "$CLOUD_EDGE_COUNT" "$TOTAL_SECONDS"
  exit 0
fi

say "Retrieve current-run context"
RESP="$(curl -fsS -X POST "$PIPELINE_URL/retrieve" \
  -H 'content-type: application/json' \
  -d "{
    \"correlation_id\": \"smoke-$RUN_ID\",
    \"identity\": {\"principal\":\"local-dev\",\"roles\":[\"admin\",\"reader\"],\"tenant\":\"default\"},
    \"tool\": \"retrieve_for_context\",
    \"query\": \"amber-context protocol\",
    \"top_k\": 10,
    \"token_budget\": 2000
  }")"
printf '%s' "$RESP" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
prefix = sys.argv[1]
assert any(item["source_uri"].startswith(prefix) for item in payload["fragments"]), payload
' "$SOURCE_PREFIX"
pass "retrieve returned current-run context"

say "Verify retrieval audit row"
AUDIT_COUNT="$(curl -fsS "$PIPELINE_URL/audit/recent?limit=20" | python3 -c '
import json, sys
run_id = sys.argv[1]
print(sum(item["correlation_id"] == f"smoke-{run_id}" for item in json.load(sys.stdin)["items"]))
' "$RUN_ID")"
[ "$AUDIT_COUNT" -ge 1 ] || fail "no current-run audit row found"
pass "current-run retrieval audit row present"

say "Vector search current-run fixture"
VS="$(curl -fsS -X POST "$PIPELINE_URL/search/vector" \
  -H 'content-type: application/json' \
  -d '{"query":"amber-context protocol","top_k":20}')"
printf '%s' "$VS" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
prefix = sys.argv[1]
assert any(item["source_uri"].startswith(prefix) for item in payload["hits"]), payload
' "$SOURCE_PREFIX"
pass "vector search returned a current-run hit"

say "Tombstone a current-run chunk"
ENTITY_ID="$(psql_value "
  SELECT entity_id
  FROM opencg.entity
  WHERE source_uri LIKE '${SOURCE_PREFIX}%'
    AND parent_entity_id IS NOT NULL
    AND tombstoned_at IS NULL
  ORDER BY created_at
  LIMIT 1
")"
[ -n "$ENTITY_ID" ] || fail "no current-run chunk available for tombstone"
TS="$(curl -fsS -X DELETE "$PIPELINE_URL/entities/$ENTITY_ID")"
printf '%s' "$TS" | python3 -c \
  'import json,sys; assert json.load(sys.stdin).get("tombstoned_at")'
pass "tombstoned current-run entity $ENTITY_ID"

say "Verify the tombstoned chunk is no longer retrieved"
AFTER="$(curl -fsS -X POST "$PIPELINE_URL/retrieve" \
  -H 'content-type: application/json' \
  -d "{
    \"correlation_id\": \"smoke-$RUN_ID-after-tombstone\",
    \"identity\": {\"principal\":\"local-dev\",\"roles\":[\"admin\",\"reader\"],\"tenant\":\"default\"},
    \"tool\": \"retrieve_for_context\",
    \"query\": \"amber-context protocol\",
    \"top_k\": 10,
    \"token_budget\": 2000
  }")"
printf '%s' "$AFTER" | python3 -c '
import json, sys
entity_id = sys.argv[1]
returned = [item["entity_id"] for item in json.load(sys.stdin)["fragments"]]
assert entity_id not in returned, f"tombstoned {entity_id} still retrieved: {returned}"
' "$ENTITY_ID"
pass "tombstoned entity excluded from /retrieve"

say "Verify ingestion connector proxy"
curl -fsS "$PIPELINE_URL/ingestion/connectors" | python3 -c '
import json, sys
assert any(item["name"] == "git" and item["supported"] for item in json.load(sys.stdin))
'
pass "git connector advertised"

say "Verify current-run Graphifyy graph"
CODE_COUNTS="$(psql_value "
  SELECT
    count(DISTINCT c.concept_id),
    count(DISTINCT e.edge_id),
    count(DISTINCT chunk.entity_id)
  FROM opencg.entity parent
  LEFT JOIN opencg.concept c ON c.source_entity_id = parent.entity_id
  LEFT JOIN opencg.relationship_evidence ev ON ev.entity_id = parent.entity_id
  LEFT JOIN opencg.relationship_edge e
    ON e.edge_id = ev.edge_id AND e.extractor_version LIKE 'graphifyy/%'
  LEFT JOIN opencg.entity chunk
    ON chunk.parent_entity_id = parent.entity_id AND chunk.metadata ? 'symbol_id'
  WHERE parent.source_uri LIKE '${SOURCE_PREFIX}%'
")"
IFS='|' read -r CONCEPT_COUNT CODE_EDGE_COUNT SYMBOL_COUNT <<<"$CODE_COUNTS"
if [ "${CONCEPT_COUNT:-0}" -lt 2 ] || [ "${CODE_EDGE_COUNT:-0}" -lt 1 ] || [ "${SYMBOL_COUNT:-0}" -lt 1 ]; then
  fail "current-run code graph incomplete: concepts=$CONCEPT_COUNT edges=$CODE_EDGE_COUNT symbols=$SYMBOL_COUNT"
fi
pass "code graph populated: concepts=$CONCEPT_COUNT edges=$CODE_EDGE_COUNT symbols=$SYMBOL_COUNT"

say "Verify relationship vocabulary"
VOCAB="$(curl -fsS "$PIPELINE_URL/graph/vocab")"
EXPECTED_VOCAB="depends_on defined_in supersedes mentions related_to causes derived_from"
MISSING_VOCAB="$(printf '%s' "$VOCAB" | python3 -c '
import json, sys
expected = set(sys.argv[1].split())
actual = {item["name"] for item in json.load(sys.stdin)["items"]}
print(" ".join(sorted(expected - actual)))
' "$EXPECTED_VOCAB")"
[ -z "$MISSING_VOCAB" ] || fail "missing relationship names: $MISSING_VOCAB"
pass "seven seeded relationship names present"

say "Resolve current-run candidate relationship"
EDGE_ROW="$(psql_value "
  SELECT e.edge_id, e.from_concept_id
  FROM opencg.relationship_edge e
  JOIN opencg.relationship_evidence ev ON ev.edge_id = e.edge_id
  JOIN opencg.entity entity ON entity.entity_id = ev.entity_id
  WHERE entity.source_uri LIKE '${SOURCE_PREFIX}%'
    AND e.state = 'candidate'
    AND e.extractor_version LIKE 'text-extractor/%'
  ORDER BY e.confidence DESC, e.created_at DESC
  LIMIT 1
")"
IFS='|' read -r EDGE_ID CONCEPT_ID <<<"$EDGE_ROW"
[ -n "$EDGE_ID" ] && [ -n "$CONCEPT_ID" ] || fail "no current-run candidate edge found"
CANDIDATES="$(curl -fsS "$PIPELINE_URL/graph/edges?state=candidate&limit=200")"
printf '%s' "$CANDIDATES" | python3 -c '
import json, sys
edge_id = sys.argv[1]
assert any(item["edge_id"] == edge_id for item in json.load(sys.stdin)["items"])
' "$EDGE_ID"
pass "candidate review queue contains current-run edge $EDGE_ID"

say "Traverse current-run concept"
TRAVERSE="$(curl -fsS "$PIPELINE_URL/graph/traverse?concept_id=$CONCEPT_ID&depth=2&include_candidates=true")"
TRAVERSE_EDGES="$(printf '%s' "$TRAVERSE" | python3 -c \
  'import json,sys; print(len(json.load(sys.stdin)["edges"]))')"
[ "$TRAVERSE_EDGES" -ge 1 ] || fail "graph traversal returned no edges"
pass "graph traversal returned $TRAVERSE_EDGES edge(s)"

say "Promote current-run candidate and verify graph audit"
PROMOTED="$(curl -fsS -X POST "$PIPELINE_URL/graph/edges/$EDGE_ID/promote" \
  -H 'content-type: application/json' \
  -d '{"reason":"deterministic full-smoke verification"}')"
printf '%s' "$PROMOTED" | python3 -c \
  'import json,sys; assert json.load(sys.stdin)["state"] == "confirmed"'
GRAPH_AUDIT_COUNT="$(psql_value "
  SELECT count(*)
  FROM opencg.graph_audit_log
  WHERE target_kind = 'edge'
    AND target_id = '$EDGE_ID'
    AND to_state = 'confirmed'
")"
[ "${GRAPH_AUDIT_COUNT:-0}" -ge 1 ] || fail "no graph audit row found for $EDGE_ID"
pass "candidate promoted and append-only graph audit row written"

OTEL_ENDPOINT="$("${COMPOSE[@]}" exec -T ingestion sh -c \
  'printf "%s" "${OTEL_EXPORTER_OTLP_ENDPOINT:-http://otel-collector:4318}"')"
OTEL_ENDPOINT_NORMALIZED="$(printf '%s' "$OTEL_ENDPOINT" | tr '[:upper:]' '[:lower:]')"
case "$OTEL_ENDPOINT_NORMALIZED" in
  ""|none|off|disabled)
    say "Telemetry verification"
    pass "telemetry verification skipped because OTLP export is explicitly disabled"
    ;;
  *)
    say "Verify current smoke spans reached the collector"
    FOUND_SPANS=false
    for _ in $(seq 1 20); do
      OTEL_LOGS="$("${COMPOSE[@]}" logs --since "$SMOKE_STARTED_AT" otel-collector 2>&1 || true)"
      if grep -q 'service.name.*opencg-ingestion' <<<"$OTEL_LOGS" \
        && grep -q 'pipeline.graph_extract_code' <<<"$OTEL_LOGS" \
        && grep -q 'pipeline.graph_extract_text' <<<"$OTEL_LOGS" \
        && grep -q 'tokens_in' <<<"$OTEL_LOGS"; then
        FOUND_SPANS=true
        break
      fi
      sleep 1
    done
    [ "$FOUND_SPANS" = true ] || fail "collector did not expose expected ingestion/extraction spans"
    pass "collector received code/text extraction spans with token attributes"
    ;;
esac

TOTAL_SECONDS=$((SECONDS - START_SECONDS))
[ "$TOTAL_SECONDS" -le "$SMOKE_TIMEOUT_SECONDS" ] || fail "smoke exceeded overall deadline"
say "Smoke test PASSED"
printf 'run_id=%s mode=%s parents=%s chunks=%s duration=%ss\n' \
  "$RUN_ID" "$SMOKE_CHAT_MODE" "$PARENTS" "$CHUNKS" "$TOTAL_SECONDS"
