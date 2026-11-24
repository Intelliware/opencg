## MODIFIED Requirements

### Requirement: Per-stage token accounting

Every stage that invokes a model SHALL record `model`, `provider`, `tokens_in`, `tokens_out` (when the response carries them), `latency_ms` and `cost_usd` on its OTel span AND increment `opencg_tokens_total{stage,model,provider,tenant,direction}` AND increment `opencg_cost_usd_total{provider,model,tenant}` by the cost computed from the configured price table (see the observability capability, "Cost computed wherever tokens are counted").

Text relationship extraction MUST use `stage="graph_extract_text"` and emit an OTel span named `pipeline.graph_extract_text`. Deterministic Graphifyy extraction MUST use `stage="graph_extract_code"` and emit an OTel span named `pipeline.graph_extract_code` with `model="graphifyy"`, `provider="graphifyy"`, and zero tokens; it MUST NOT increment the token counter or the cost counter.

Embedding calls made while ingesting chunks MUST use `stage="ingest_embed"`. The ingestion run MUST count the tokens of every successful embedding call, and the counter increments MUST be visible through the ingestion service's `/metrics` even when the run was started from the CLI.

#### Scenario: Graph extraction token accounting

- **WHEN** the ingestion service runs the extractor on a chunk and the chat model returns a usable response
- **THEN** an OTel span `pipeline.graph_extract_text` is emitted with `model`, `provider`, `tokens_in`, `tokens_out`, `latency_ms`, and `cost_usd`
- **AND** `opencg_tokens_total{stage="graph_extract_text"}` increases by the recorded counts
- **AND** `opencg_cost_usd_total` increases by the cost the price table gives for those counts

#### Scenario: Code extraction emits a token-zero span

- **WHEN** the ingestion service runs Graphifyy on a code file
- **THEN** an OTel span `pipeline.graph_extract_code` is emitted with zero token attributes
- **AND** `opencg_tokens_total{stage="graph_extract_code"}` is not incremented
- **AND** `opencg_cost_usd_total{provider="graphifyy"}` is not incremented

#### Scenario: Ingestion embedding is counted

- **WHEN** an ingestion run embeds N chunks successfully
- **THEN** `opencg_tokens_total{stage="ingest_embed",direction="in"}` increases by the sum of those calls' `tokens_in`

#### Scenario: Other stages unchanged

- **WHEN** a `/retrieve` call completes
- **THEN** the existing token attribution for `hybrid_retrieval` and the vector-search admin endpoint remains as before
- **AND** each of those increments is paired with a cost increment
