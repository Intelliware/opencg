## ADDED Requirements

### Requirement: MCP tool surface

The system SHALL expose an MCP server (TypeScript) that advertises the tools `search`, `retrieve_for_context`, `get_entity`, `traverse_graph`, and `submit_feedback`. Each tool SHALL declare a JSON schema for its inputs and outputs and return structured responses suitable for downstream model consumption.

#### Scenario: Client discovers available tools

- **WHEN** an MCP client calls `tools/list` against the server
- **THEN** the server returns the five tools above with input and output schemas
- **AND** each tool name is namespaced under `opencg/<tool>`

#### Scenario: `retrieve_for_context` returns structured payload

- **WHEN** a client calls `opencg/retrieve_for_context` with a query and a token budget
- **THEN** the response contains an ordered list of context fragments, each with `id`, `source_uri`, `score`, `entitlement_classification`, and `tokens`
- **AND** the response contains a `correlation_id` matching the audit record for the request
- **AND** the total tokens across fragments does not exceed the requested budget

### Requirement: Identity and correlation propagation

The MCP server SHALL propagate an identity context (principal, roles, tenant) and a correlation ID to the retrieval pipeline on every request. In v0 the identity context MAY be sourced from a stubbed configuration, but the propagation contract MUST be present so that downstream stages see the same shape after real authentication is added.

#### Scenario: Stubbed identity in v0

- **WHEN** the server starts in v0 and receives any tool call
- **THEN** it attaches the configured stub principal and the configured stub roles to the outbound pipeline request
- **AND** it generates a new correlation ID per request if none is supplied by the client

#### Scenario: Caller-supplied correlation ID is preserved

- **WHEN** a client sets the `x-correlation-id` field on a tool call
- **THEN** the server uses that value for downstream propagation and audit indexing

### Requirement: Per-request telemetry envelope

Every MCP request SHALL emit an OpenTelemetry span that records `tool_name`, `principal`, `correlation_id`, `latency_ms`, `tokens_in`, `tokens_out`, and outcome (`ok` / `error_code`). Token counts SHALL aggregate across the pipeline stages.

#### Scenario: Span emitted on successful call

- **WHEN** any tool call completes successfully
- **THEN** the server emits a span named `mcp.<tool>` with the required attributes
- **AND** the span is linked to the pipeline trace via the correlation ID

### Requirement: Feedback submission

The `submit_feedback` tool SHALL accept a `correlation_id`, a `rating` (`useful` / `partially_useful` / `not_useful`), and optional `notes`, and SHALL persist the feedback to the usage-feedback stream consumed by background enrichment.

#### Scenario: Client submits feedback

- **WHEN** a client calls `submit_feedback` with a valid correlation ID and rating
- **THEN** the system stores a feedback record keyed to the original audit record
- **AND** the record is observable on the usage-feedback stream within one second
