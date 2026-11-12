# Shared helpers for tests/smoke/run.sh and tests/smoke/fixture.sh. Source it;
# don't execute it. Sets ROOT and COMPOSE.
#
# Set OPENCG_E2E=1 to add the e2e overlay on top of the smoke overlay (see
# infra/compose/docker-compose.e2e.yml). Set SMOKE_OBS=1 (what `make smoke-obs`
# does) to add the OPTIONAL observability overlay (Prometheus, Tempo, Grafana;
# infra/compose/docker-compose.observability.yml). OPENCG_ROOT points the
# helpers at another checkout's compose files and .env.

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
if [ "${SMOKE_OBS:-0}" = "1" ]; then
  COMPOSE+=(-f "$ROOT/infra/compose/docker-compose.observability.yml")
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
      -e OPENCG__PROVIDERS__CHAT__PROVIDER=ollama
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

# ---------------------------------------------------------------------------
# Metrics helpers (default smoke: /metrics on every service, no Prometheus).
# ---------------------------------------------------------------------------

# metrics_missing_families: read Prometheus text from stdin, print the given
# families that have neither a `# TYPE` line nor a sample. Counters are named
# with their `_total` suffix, as they appear in the exposition.
metrics_missing_families() {
  python3 -c '
import re, sys
text = sys.stdin.read()
present = set(re.findall(r"^# TYPE (\S+) ", text, re.M))
present |= set(re.findall(r"^([A-Za-z_:][A-Za-z0-9_:]*)", text, re.M))
for family in sys.argv[1:]:
    base = family[:-6] if family.endswith("_total") else family
    names = {family, base, base + "_total", base + "_bucket", base + "_count"}
    if not names & present:
        print(family)
' "$@"
}

# metrics_sum NAME [LABEL_MATCHER...]: read Prometheus text from stdin, print
# the sum of NAME samples whose label set contains every given `key="value"`
# matcher (0 when there are none).
metrics_sum() {
  python3 -c '
import re, sys
name, matchers = sys.argv[1], sys.argv[2:]
total = 0.0
for line in sys.stdin:
    match = re.match(r"^([A-Za-z_:][A-Za-z0-9_:]*)(\{[^}]*\})?\s+(\S+)", line)
    if not match or match.group(1) != name:
        continue
    labels = match.group(2) or ""
    if all(m in labels for m in matchers):
        total += float(match.group(3))
print(f"{total:g}")
' "$@"
}

# ---------------------------------------------------------------------------
# MCP over Streamable HTTP: initialize, call one tool, close the session.
# ---------------------------------------------------------------------------

# mcp_retrieve MCP_URL QUERY: call opencg/retrieve_for_context over HTTP and
# print the result's correlation_id. Sends OPENCG__MCP__HTTP_TOKEN as a bearer
# token when it is set (in the environment or .env); the token is never printed.
mcp_retrieve() {
  local token
  token="$(cfg OPENCG__MCP__HTTP_TOKEN "")"
  MCP_TOKEN="$token" python3 - "$1" "$2" <<'PY'
import json, os, sys, urllib.error, urllib.request

url, query = sys.argv[1], sys.argv[2]
token = os.environ.get("MCP_TOKEN", "").strip()
session = None


def post(payload, method="POST"):
    global session
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2025-03-26",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    if session:
        headers["mcp-session-id"] = session
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            session = response.headers.get("mcp-session-id") or session
            body = response.read().decode()
            ctype = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"MCP {method} failed: HTTP {exc.code}") from None
    if not body.strip():
        return []
    if "text/event-stream" in ctype:
        return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]
    return [json.loads(body)]


def result_for(messages, request_id):
    for message in messages:
        if message.get("id") == request_id:
            if "error" in message:
                raise SystemExit(f"MCP error: {message['error']}")
            return message["result"]
    raise SystemExit(f"no MCP response for request {request_id}")


result_for(post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "opencg-smoke", "version": "0"},
}}), 1)
post({"jsonrpc": "2.0", "method": "notifications/initialized"})
result = result_for(post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
    "name": "opencg/retrieve_for_context",
    "arguments": {"query": query, "top_k": 5, "token_budget": 1000},
}}), 2)
if result.get("isError"):
    raise SystemExit(f"tool call failed: {result['content'][0]['text']}")
payload = json.loads(result["content"][0]["text"])
try:
    post(None, method="DELETE")
except SystemExit:
    pass  # closing the session is best effort
print(payload["correlation_id"])
PY
}

# ---------------------------------------------------------------------------
# Observability overlay helpers (smoke-obs only).
# ---------------------------------------------------------------------------

# http_code URL [CURL_ARGS...]: print only the HTTP status of a GET.
http_code() {
  local url="$1"
  shift
  curl -s -o /dev/null -w '%{http_code}' "$@" "$url" || true
}

# prom_targets_down PROM_URL JOB...: print each job with no `up` target.
prom_targets_down() {
  local prom="$1"
  shift
  curl -fsS "$prom/api/v1/targets?state=active" 2>/dev/null | python3 -c '
import json, sys
try:
    targets = json.load(sys.stdin)["data"]["activeTargets"]
except Exception:
    targets = []
up = {t["labels"].get("job") for t in targets if t.get("health") == "up"}
for job in sys.argv[1:]:
    if job not in up:
        print(job)
' "$@"
}

# prom_scalar PROM_URL EXPR: print the first value of an instant query, or
# nothing when the result is empty.
prom_scalar() {
  curl -fsS -G "$1/api/v1/query" --data-urlencode "query=$2" 2>/dev/null | python3 -c '
import json, sys
try:
    result = json.load(sys.stdin)["data"]["result"]
except Exception:
    result = []
if result:
    print(result[0]["value"][1])
'
}

# tempo_trace_check TEMPO_URL CORRELATION_ID SPAN...: search Tempo for the
# correlation ID and check the trace. Prints "ok <trace_id>" when exactly one
# trace matches, every listed span name is in it, all its spans share one
# trace_id and every span carries correlation_id; otherwise prints why not.
tempo_trace_check() {
  local tempo="$1" cid="$2"
  shift 2
  local now
  now="$(date +%s)"
  curl -fsS -G "$tempo/api/search" \
    --data-urlencode "q={ span.correlation_id = \"$cid\" }" \
    --data-urlencode "start=$((now - 3600))" --data-urlencode "end=$((now + 300))" \
    2>/dev/null | TEMPO_URL="$tempo" CID="$cid" python3 -c '
import json, os, sys, urllib.request
try:
    traces = json.load(sys.stdin).get("traces") or []
except Exception:
    traces = []
if len(traces) != 1:
    print(f"search found {len(traces)} traces for the correlation_id (want 1)")
    raise SystemExit(0)
trace_id = traces[0]["traceID"]
tempo_url, cid = os.environ["TEMPO_URL"], os.environ["CID"]
url = f"{tempo_url}/api/v2/traces/{trace_id}"
with urllib.request.urlopen(url, timeout=10) as response:
    trace = json.load(response).get("trace", {})
names, trace_ids, missing_cid = set(), set(), set()
for resource in trace.get("resourceSpans", []):
    for scope in resource.get("scopeSpans", []):
        for span in scope.get("spans", []):
            names.add(span["name"])
            trace_ids.add(span["traceId"])
            attrs = {a["key"]: a.get("value", {}).get("stringValue") for a in span.get("attributes", [])}
            if attrs.get("correlation_id") != cid:
                missing_cid.add(span["name"])
wanted = set(sys.argv[1:])
if wanted - names:
    print(f"trace {trace_id} lacks spans: {sorted(wanted - names)}")
elif len(trace_ids) != 1:
    print(f"spans carry {len(trace_ids)} different trace ids")
elif missing_cid:
    print(f"spans without correlation_id={cid}: {sorted(missing_cid)}")
else:
    print(f"ok {trace_id} spans={len(names)}")
' "$@"
}
