## MODIFIED Requirements

### Requirement: Observable smoke path

The development compose profile SHALL include a healthy OpenTelemetry Collector accepting OTLP/HTTP traffic from openCG services. The default full smoke MUST verify that the collector receives ingestion resource data and both `pipeline.graph_extract_code` and `pipeline.graph_extract_text` spans generated after the smoke starts.

The default full smoke MUST also scrape `/metrics` on the pipeline, the ingestion service and the MCP server, and MUST fail if any metric family that service is required to expose (see the observability capability) is missing, or if `opencg_tokens_total{stage="ingest_embed"}` on the ingestion service did not increase during the smoke. These checks MUST NOT need Prometheus, Tempo or Grafana.

Telemetry assertions MAY be skipped only when the operator explicitly sets the exporter endpoint to `none`, `off`, `disabled`, or an empty value. The skip MUST be visible in smoke output. The `/metrics` assertions MUST still run in that mode.

The repository SHALL also provide an opt-in observability smoke (`make smoke-obs`). It applies the observability overlay on top of the smoke overlay, runs the default smoke, and then MUST verify, within a bounded wait:

1. the Prometheus targets API reports the pipeline, ingestion, MCP server and collector targets as `up`;
2. Prometheus returns a non-zero increase for `opencg_tokens_total` and a present `opencg_cost_usd_total` series;
3. an MCP `retrieve_for_context` call made by the smoke can be found in Tempo by its `correlation_id`, as a single trace containing `mcp.retrieve_for_context` and `pipeline.hybrid_retrieval`;
4. the Grafana search API, called with the admin credentials, lists every dashboard in `infra/grafana/dashboards/` in the "openCG" folder;
5. the same Grafana API refuses the request without credentials (HTTP 401).

#### Scenario: Collector receives extraction spans

- **WHEN** the default full smoke ingests the mixed prose/code fixture
- **THEN** collector output contains resource data for `service.name = opencg-ingestion`
- **AND** contains a `pipeline.graph_extract_code` span
- **AND** contains a `pipeline.graph_extract_text` span

#### Scenario: Default smoke checks metric endpoints

- **WHEN** the default full smoke has ingested the fixture and run a retrieval
- **THEN** each service's `/metrics` contains its required metric families
- **AND** the ingestion service's `opencg_tokens_total{stage="ingest_embed"}` is higher than it was before the smoke started

#### Scenario: Explicit offline mode skips telemetry assertion

- **WHEN** the exporter endpoint is explicitly disabled
- **THEN** ingestion does not retry a missing collector
- **AND** the smoke reports that telemetry verification was skipped
- **AND** the `/metrics` assertions still run

#### Scenario: Observability smoke finds the trace in Tempo

- **WHEN** an operator runs `make smoke-obs`
- **THEN** the smoke prints a pass line for Prometheus targets, metric series, the Tempo trace, the Grafana dashboards and the Grafana anonymous-access refusal
- **AND** exits non-zero, naming the failed check, if any of them does not pass within its bounded wait
