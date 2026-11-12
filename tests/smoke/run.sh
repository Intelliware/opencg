#!/usr/bin/env bash
# Deterministic end-to-end verification for an already-built healthy dev stack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=tests/smoke/lib.sh
source "$ROOT/tests/smoke/lib.sh"

PIPELINE_URL="${PIPELINE_URL:-http://localhost:$(cfg OPENCG__PIPELINE__HOST_PORT 8000)}"
QDRANT_URL="${QDRANT_URL:-http://localhost:$(cfg OPENCG__QDRANT__HOST_PORT 6333)}"
INGESTION_URL="${INGESTION_URL:-http://localhost:$(cfg OPENCG__INGESTION__HOST_PORT 8100)}"
MCP_URL="${MCP_URL:-http://localhost:$(cfg OPENCG__MCP__HOST_PORT 8181)}"
# SMOKE_OBS=1 (`make smoke-obs`) also applies the OPTIONAL observability overlay
# and checks Prometheus, Tempo and Grafana after the default smoke.
SMOKE_OBS="${SMOKE_OBS:-0}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:$(cfg OPENCG__PROMETHEUS__HOST_PORT 9090)}"
TEMPO_URL="${TEMPO_URL:-http://localhost:$(cfg OPENCG__TEMPO__HOST_PORT 3200)}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:$(cfg OPENCG__GRAFANA__HOST_PORT 3030)}"
SMOKE_OBS_WAIT_SECONDS="${SMOKE_OBS_WAIT_SECONDS:-120}"
if [ "$SMOKE_OBS" = "1" ]; then
  SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-600}"
else
  SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-300}"
fi
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
if [ "$SMOKE_OBS" = "1" ] && [ "$SMOKE_CHAT_MODE" != "stub" ]; then
  fail "smoke-obs runs with the deterministic chat stub only (SMOKE_CHAT_MODE=stub)"
fi

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

# Wait until COMMAND succeeds, at most SECONDS; print its last output.
wait_until() {
  local seconds=$1
  shift
  local deadline=$((SECONDS + seconds))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if "$@"; then
      return 0
    fi
    sleep 3
  done
  return 1
}

if [ "$SMOKE_OBS" = "1" ]; then
  say "Apply the smoke + observability overlays (chat stub, fixture mount, Prometheus, Tempo, Grafana)"
  "${COMPOSE[@]}" up -d --wait smoke-chat ingestion otel-collector prometheus tempo grafana
else
  say "Apply the smoke overlay (chat stub + fixture mount)"
  "${COMPOSE[@]}" up -d --wait smoke-chat ingestion
fi

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

say "Record ingestion embedding tokens before the run"
INGEST_EMBED_BEFORE="$(curl -fsS "$INGESTION_URL/metrics" | metrics_sum opencg_tokens_total 'stage="ingest_embed"')" \
  || fail "ingestion /metrics is not reachable at $INGESTION_URL/metrics"
pass "ingestion opencg_tokens_total{stage=\"ingest_embed\"} = $INGEST_EMBED_BEFORE"

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

say "Call retrieve_for_context through the MCP server (HTTP transport)"
MCP_CORRELATION_ID="$(mcp_retrieve "$MCP_URL/mcp" "amber-context protocol")" \
  || fail "MCP retrieve_for_context call failed"
[ -n "$MCP_CORRELATION_ID" ] || fail "MCP result had no correlation_id"
pass "MCP retrieve_for_context returned correlation_id $MCP_CORRELATION_ID"

# Required families per service (observability spec). These need no
# Prometheus, Tempo or Grafana, and run even with OTLP export disabled.
# Ingestion serves a multiprocess registry, which only lists families that
# some process has written to, so it is checked for the families a
# successful git run always writes.
say "Verify /metrics on the pipeline, ingestion service and MCP server"
PIPELINE_FAMILIES="opencg_requests_total opencg_stage_latency_seconds opencg_tokens_total opencg_cost_usd_total opencg_cost_unpriced_tokens_total opencg_provider_errors_total opencg_audit_writes_total"
INGESTION_FAMILIES="opencg_ingestion_runs_total opencg_ingestion_documents_total opencg_ingestion_chunks_total opencg_ingestion_run_duration_seconds opencg_tokens_total"
MCP_FAMILIES="opencg_requests_total opencg_stage_latency_seconds"
PIPELINE_METRICS="$(curl -fsS "$PIPELINE_URL/metrics")" || fail "pipeline /metrics unreachable"
INGESTION_METRICS="$(curl -fsS "$INGESTION_URL/metrics")" || fail "ingestion /metrics unreachable"
MCP_METRICS="$(curl -fsS "$MCP_URL/metrics")" || fail "MCP server /metrics unreachable (it must not need the bearer token)"
# shellcheck disable=SC2086 # the family lists are intentionally word-split
MISSING="$(printf '%s' "$PIPELINE_METRICS" | metrics_missing_families $PIPELINE_FAMILIES)"
[ -z "$MISSING" ] || fail "pipeline /metrics lacks: $(echo $MISSING)"
# shellcheck disable=SC2086
MISSING="$(printf '%s' "$INGESTION_METRICS" | metrics_missing_families $INGESTION_FAMILIES)"
[ -z "$MISSING" ] || fail "ingestion /metrics lacks: $(echo $MISSING)"
# shellcheck disable=SC2086
MISSING="$(printf '%s' "$MCP_METRICS" | metrics_missing_families $MCP_FAMILIES)"
[ -z "$MISSING" ] || fail "MCP server /metrics lacks: $(echo $MISSING)"
MCP_STAGE_COUNT="$(printf '%s' "$MCP_METRICS" | metrics_sum opencg_stage_latency_seconds_count 'stage="mcp"')"
[ "$(python3 -c 'import sys; print(float(sys.argv[1]) > 0)' "$MCP_STAGE_COUNT")" = True ] \
  || fail "MCP server has no opencg_stage_latency_seconds{stage=\"mcp\"} observation after a tool call"
SUCCEEDED_RUNS="$(printf '%s' "$INGESTION_METRICS" | metrics_sum opencg_ingestion_runs_total 'connector="git"' 'status="succeeded"')"
[ "$(python3 -c 'import sys; print(float(sys.argv[1]) >= 1)' "$SUCCEEDED_RUNS")" = True ] \
  || fail "ingestion /metrics shows no succeeded git run (CLI runs must reach the server's registry)"
INGEST_EMBED_AFTER="$(printf '%s' "$INGESTION_METRICS" | metrics_sum opencg_tokens_total 'stage="ingest_embed"')"
[ "$(python3 -c 'import sys; print(float(sys.argv[2]) > float(sys.argv[1]))' \
  "$INGEST_EMBED_BEFORE" "$INGEST_EMBED_AFTER")" = True ] \
  || fail "ingest_embed tokens did not increase ($INGEST_EMBED_BEFORE -> $INGEST_EMBED_AFTER)"
pass "required metric families present on all three services"
pass "ingest_embed tokens increased: $INGEST_EMBED_BEFORE -> $INGEST_EMBED_AFTER"

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

if [ "$SMOKE_OBS" = "1" ]; then
  say "Observability: Tempo ready"
  wait_until "$SMOKE_OBS_WAIT_SECONDS" sh -c "curl -fsS '$TEMPO_URL/ready' >/dev/null 2>&1" \
    || fail "Tempo not ready at $TEMPO_URL/ready within ${SMOKE_OBS_WAIT_SECONDS}s"
  pass "Tempo is ready"

  say "Observability: Prometheus targets up"
  PROM_JOBS="pipeline ingestion mcp-server otel-collector"
  targets_up() {
    # shellcheck disable=SC2086
    TARGETS_DOWN="$(prom_targets_down "$PROMETHEUS_URL" $PROM_JOBS)"
    [ -z "$TARGETS_DOWN" ]
  }
  TARGETS_DOWN=""
  wait_until "$SMOKE_OBS_WAIT_SECONDS" targets_up \
    || fail "Prometheus targets not up within ${SMOKE_OBS_WAIT_SECONDS}s: $(echo $TARGETS_DOWN)"
  pass "Prometheus targets up: $PROM_JOBS"

  # A fresh Prometheus cannot see an increase in its first sample of a
  # series. Earlier smoke stages already made retrievals, so wait until
  # Prometheus holds a sample of the pipeline's retrieval token series, then
  # make the traced MCP call (which spends embedding tokens) and compare.
  TOKENS_QUERY='sum(opencg_tokens_total{job="pipeline",stage="hybrid_retrieval"})'
  TOKENS_BEFORE=""
  tokens_scraped() {
    TOKENS_BEFORE="$(prom_scalar "$PROMETHEUS_URL" "$TOKENS_QUERY")"
    [ -n "$TOKENS_BEFORE" ]
  }
  wait_until "$SMOKE_OBS_WAIT_SECONDS" tokens_scraped \
    || fail "Prometheus has no pipeline retrieval token sample within ${SMOKE_OBS_WAIT_SECONDS}s"

  say "Observability: traced MCP call"
  OBS_CORRELATION_ID="$(mcp_retrieve "$MCP_URL/mcp" "amber-context protocol")" \
    || fail "MCP retrieve_for_context call failed"
  pass "MCP retrieve_for_context correlation_id $OBS_CORRELATION_ID"

  say "Observability: token and cost series in Prometheus"
  tokens_increased() {
    local value
    value="$(prom_scalar "$PROMETHEUS_URL" "$TOKENS_QUERY")"
    [ -n "$value" ] && python3 -c 'import sys; raise SystemExit(0 if float(sys.argv[1]) > float(sys.argv[2]) else 1)' "$value" "$TOKENS_BEFORE"
  }
  wait_until "$SMOKE_OBS_WAIT_SECONDS" tokens_increased \
    || fail "Prometheus shows no increase in opencg_tokens_total within ${SMOKE_OBS_WAIT_SECONDS}s"
  COST_SERIES="$(prom_scalar "$PROMETHEUS_URL" 'count(opencg_cost_usd_total)')"
  [ -n "$COST_SERIES" ] || fail "Prometheus has no opencg_cost_usd_total series"
  pass "opencg_tokens_total increased past $TOKENS_BEFORE; $COST_SERIES opencg_cost_usd_total series present"

  say "Observability: one connected trace in Tempo"
  TRACE_SPANS="mcp.retrieve_for_context pipeline.retrieve pipeline.identity pipeline.hybrid_retrieval pipeline.assemble model.embed"
  trace_found() {
    # shellcheck disable=SC2086
    TRACE_RESULT="$(tempo_trace_check "$TEMPO_URL" "$OBS_CORRELATION_ID" $TRACE_SPANS)"
    case "$TRACE_RESULT" in ok\ *) return 0 ;; *) return 1 ;; esac
  }
  TRACE_RESULT=""
  wait_until "$SMOKE_OBS_WAIT_SECONDS" trace_found \
    || fail "Tempo trace for correlation_id $OBS_CORRELATION_ID not complete: ${TRACE_RESULT:-no result}"
  pass "Tempo trace ${TRACE_RESULT#ok } has $TRACE_SPANS, one trace_id, correlation_id on every span"

  say "Observability: Grafana dashboards"
  GRAFANA_PASSWORD="$(cfg OPENCG__GRAFANA__ADMIN_PASSWORD admin)"
  wait_until "$SMOKE_OBS_WAIT_SECONDS" sh -c "curl -fsS '$GRAFANA_URL/api/health' >/dev/null 2>&1" \
    || fail "Grafana not healthy at $GRAFANA_URL within ${SMOKE_OBS_WAIT_SECONDS}s"
  EXPECTED_UIDS="$(python3 -c '
import json, pathlib, sys
print(" ".join(sorted(json.loads(p.read_text())["uid"] for p in pathlib.Path(sys.argv[1]).glob("*.json"))))
' "$ROOT/infra/grafana/dashboards")"
  dashboards_listed() {
    GRAFANA_UIDS="$(curl -fsS -u "admin:$GRAFANA_PASSWORD" \
      "$GRAFANA_URL/api/search?folderUIDs=opencg&type=dash-db" 2>/dev/null | python3 -c '
import json, sys
try:
    items = json.load(sys.stdin)
except Exception:
    items = []
print(" ".join(sorted(i["uid"] for i in items if i.get("folderTitle") == "openCG")))
')"
    [ "$GRAFANA_UIDS" = "$EXPECTED_UIDS" ]
  }
  GRAFANA_UIDS=""
  wait_until "$SMOKE_OBS_WAIT_SECONDS" dashboards_listed \
    || fail "Grafana openCG folder lists [$GRAFANA_UIDS], expected [$EXPECTED_UIDS]"
  pass "Grafana lists every dashboard in the openCG folder: $EXPECTED_UIDS"

  say "Observability: Grafana refuses anonymous access"
  ANON_SEARCH="$(http_code "$GRAFANA_URL/api/search?folderUIDs=opencg")"
  ANON_DASHBOARD="$(http_code "$GRAFANA_URL/api/dashboards/uid/opencg-requests")"
  [ "$ANON_SEARCH" = 401 ] && [ "$ANON_DASHBOARD" = 401 ] \
    || fail "Grafana answered unauthenticated requests with $ANON_SEARCH / $ANON_DASHBOARD (want 401)"
  pass "Grafana returns 401 without credentials"
fi

TOTAL_SECONDS=$((SECONDS - START_SECONDS))
[ "$TOTAL_SECONDS" -le "$SMOKE_TIMEOUT_SECONDS" ] || fail "smoke exceeded overall deadline"
if [ "$SMOKE_OBS" = "1" ]; then
  say "Observability smoke PASSED"
else
  say "Smoke test PASSED"
fi
printf 'run_id=%s mode=%s parents=%s chunks=%s duration=%ss\n' \
  "$RUN_ID" "$SMOKE_CHAT_MODE" "$PARENTS" "$CHUNKS" "$TOTAL_SECONDS"
