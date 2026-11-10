## MODIFIED Requirements

### Requirement: MCP tool surface

The system SHALL expose an MCP server (TypeScript) that advertises the tools `search`, `retrieve_for_context`, `get_entity`, `traverse_graph`, and `submit_feedback`. Each tool SHALL declare a JSON schema for its inputs and outputs.

**Thin-MVP scope:** only `opencg/retrieve_for_context` is functional end-to-end. The other four tools are advertised in `tools/list` so MCP clients see the v0 surface, but a `tools/call` for any of them SHALL return a structured error with `code = "not_implemented_in_mvp"` and a `message` naming the follow-up change that implements it.

#### Scenario: Client discovers available tools

- **WHEN** an MCP client calls `tools/list` against the server
- **THEN** the server returns the five tools above with input and output schemas
- **AND** each tool name is namespaced under `opencg/<tool>`

#### Scenario: `retrieve_for_context` returns structured payload

- **WHEN** a client calls `opencg/retrieve_for_context` with a query and a token budget
- **THEN** the response contains an ordered list of context fragments, each with `id`, `source_uri`, `score`, `entitlement_classification`, and `tokens`
- **AND** the response contains a `correlation_id` matching the audit record for the request
- **AND** the total tokens across fragments does not exceed the requested budget

#### Scenario: Deferred tools return a structured error

- **WHEN** a client calls any of `opencg/search`, `opencg/get_entity`, `opencg/traverse_graph`, or `opencg/submit_feedback`
- **THEN** the server returns `isError: true` with content describing `code = "not_implemented_in_mvp"`
- **AND** the call does NOT reach the retrieval pipeline

### Requirement: Identity and correlation propagation

The MCP server SHALL propagate an identity context (principal, roles, tenant) and a correlation ID to the retrieval pipeline on every request. In v0 the identity context is sourced from a stubbed configuration; the propagation contract MUST be present so that downstream stages see the same shape after real authentication is added.

#### Scenario: Stubbed identity in v0

- **WHEN** the server starts in v0 and receives any tool call
- **THEN** it attaches the configured stub principal and the configured stub roles to the outbound pipeline request
- **AND** it generates a new correlation ID per request if none is supplied by the client

#### Scenario: Caller-supplied correlation ID is preserved

- **WHEN** a client sets `x-correlation-id` (HTTP transport) or passes a `correlationId` (stdio transport) on a tool call
- **THEN** the server uses that value for downstream propagation and audit indexing

### Requirement: Per-request telemetry envelope

Every MCP request SHALL emit an OpenTelemetry span that records `tool_name`, `principal`, `correlation_id`, `latency_ms`, `tokens_in`, `tokens_out`, and outcome (`ok` / `error_code`). Token counts SHALL aggregate across the pipeline stages.

**Thin-MVP scope:** the span is emitted but no OTel collector is wired in this change; spans are exportable as soon as a collector is configured. The contract on the span is the load-bearing piece.

#### Scenario: Span emitted on successful call

- **WHEN** any tool call completes successfully
- **THEN** the server emits a span named `mcp.<tool>` with the required attributes
- **AND** the span is linked to the pipeline trace via the correlation ID

## ADDED Requirements

### Requirement: Health and readiness endpoints

The MCP server SHALL expose `GET /healthz` (liveness) returning `200` with `{"status":"ok"}` and `GET /readyz` returning `200` only when the retrieval pipeline's `/healthz` returns `200`. Compose health gating depends on this.

#### Scenario: Readiness reflects pipeline health

- **WHEN** the pipeline service is healthy
- **THEN** `GET /readyz` on the MCP server returns `200`

#### Scenario: Readiness fails when pipeline is unavailable

- **WHEN** the pipeline service is unreachable
- **THEN** `GET /readyz` on the MCP server returns `503` with a `status` indicating `pipeline_unavailable`
