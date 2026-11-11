# smoke-testing Specification

## Purpose

Provide a deterministic, bounded end-to-end smoke test of the running stack. It ingests a uniquely named local fixture with a chat stub, asserts only on that run's data, verifies telemetry, and offers an opt-in, capped real-provider canary.

## Requirements
### Requirement: Deterministic full-stack fixture

The project SHALL provide a committed smoke fixture that produces fewer than 20 chunks and contains both prose and supported code. Each smoke run MUST construct a uniquely named local Git repository from the fixture so all generated `source_uri` values can be attributed to that run.

The fixture MUST contain enough information to exercise vector retrieval, Graphifyy symbol extraction, text relationship extraction, graph traversal, candidate promotion, and both audit stores.

#### Scenario: Default fixture remains small

- **WHEN** the full smoke ingests the committed fixture with default chunking settings
- **THEN** ingestion reports fewer than 20 chunks
- **AND** at least one chunk contains symbol metadata
- **AND** at least one candidate relationship is supported by a fixture text chunk

#### Scenario: Repeated runs are isolated

- **WHEN** the full smoke is run twice against the same persistent development stack
- **THEN** each run uses a different `git://hive-mind-smoke-<run-id>/` source prefix
- **AND** mutations in the second run target only entities and edges supported by the second run

### Requirement: Deterministic and cloud provider modes

The default full smoke SHALL use an Ollama-compatible deterministic HTTP stub for chat extraction while continuing to use the real configured embeddings service. The stub MUST return schema-valid extraction JSON and fixed non-zero input/output token counts.

The smoke SHALL also expose an opt-in cloud mode. Cloud mode MUST require explicit selection, MUST process no more than one document and two chunks, and MUST fail clearly when provider credentials are absent.

#### Scenario: Default smoke requires no cloud credential

- **WHEN** the operator runs `bash tests/smoke/run.sh` without selecting cloud mode
- **THEN** graph text extraction calls the local deterministic chat stub
- **AND** no request is sent to an external chat provider
- **AND** candidate relationship and token-accounting assertions pass

#### Scenario: Cloud canary is bounded

- **WHEN** the operator runs the smoke with `SMOKE_CHAT_MODE=cloud` and valid provider configuration
- **THEN** ingestion sends at most two chat extraction requests
- **AND** the canary verifies a parseable response and non-zero provider token counts

#### Scenario: Cloud canary rejects missing credentials

- **WHEN** cloud mode is selected without an API key
- **THEN** the smoke exits before ingestion with a message naming the required environment variable

### Requirement: Bounded smoke execution

The full smoke SHALL complete within 300 seconds on an already-built healthy development stack. The deadline MUST be configurable, and each long-running stage MUST have its own deadline no greater than the remaining overall budget.

On timeout, assertion failure, interrupt, or normal exit, the runner MUST terminate its active child processes and remove temporary fixture data from the ingestion container. Output MUST identify the failed stage and elapsed duration.

#### Scenario: Hung ingestion is terminated

- **WHEN** the ingestion subprocess exceeds its stage deadline
- **THEN** the smoke terminates the Docker exec process and its in-container ingestion child
- **AND** exits non-zero with the stage name and elapsed time

#### Scenario: Successful smoke reports stage durations

- **WHEN** every smoke assertion passes
- **THEN** the runner prints a duration for each stage
- **AND** prints the total duration before reporting success

### Requirement: Observable smoke path

The development compose profile SHALL include a healthy OpenTelemetry Collector accepting OTLP/HTTP traffic from openCG services. The default full smoke MUST verify that the collector receives ingestion resource data and both `pipeline.graph_extract_code` and `pipeline.graph_extract_text` spans generated after the smoke starts.

Telemetry assertions MAY be skipped only when the operator explicitly sets the exporter endpoint to `none`, `off`, `disabled`, or an empty value. The skip MUST be visible in smoke output.

#### Scenario: Collector receives extraction spans

- **WHEN** the default full smoke ingests the mixed prose/code fixture
- **THEN** collector output contains resource data for `service.name = hive-mind-ingestion`
- **AND** contains a `pipeline.graph_extract_code` span
- **AND** contains a `pipeline.graph_extract_text` span

#### Scenario: Explicit offline mode skips telemetry assertion

- **WHEN** the exporter endpoint is explicitly disabled
- **THEN** ingestion does not retry a missing collector
- **AND** the smoke reports that telemetry verification was skipped

### Requirement: Qdrant compatibility

The development stack SHALL use Python Qdrant clients compatible with the configured Qdrant server minor version. The smoke MUST fail with an actionable compatibility message when the versions drift outside the supported range.

#### Scenario: Compatible client and server are quiet

- **WHEN** the development stack starts with the checked-in Qdrant dependency and image pins
- **THEN** ingestion and retrieval construct their Qdrant clients without a version incompatibility warning

#### Scenario: Incompatible version is reported

- **WHEN** the Qdrant client and server versions are outside the supported compatibility range
- **THEN** readiness or smoke fails before fixture ingestion
- **AND** the failure identifies both versions

### Requirement: Current-run assertions

Every destructive or state-changing smoke assertion SHALL first resolve a target whose source or evidence belongs to the current smoke run. The runner MUST NOT tombstone the first global entity or promote the first global candidate edge without proving run ownership.

#### Scenario: Entity tombstone targets fixture data

- **WHEN** the smoke exercises `DELETE /entities/{id}`
- **THEN** the selected entity has the current run's source URI prefix

#### Scenario: Edge promotion targets fixture evidence

- **WHEN** the smoke exercises `POST /graph/edges/{id}/promote`
- **THEN** the selected candidate edge has relationship evidence from a current-run chunk
- **AND** the resulting graph audit row names that edge

