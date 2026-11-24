## MODIFIED Requirements

### Requirement: Automatic relationship extraction

Ingestion SHALL run a *concept-and-relationship extractor* on every chunk after the chunk's vector point is upserted to Qdrant. The extractor MUST call a chat model (default: Ollama Cloud `gemma4:31b`) and request a structured JSON output containing `concepts` and `relations`. Concepts MUST be deduped against `opencg.concept` by a normalised `dedupe_key` (Unicode-folded, case-folded, whitespace-collapsed). New concepts AND new edges land in `state = "candidate"`.

The extractor MUST be best-effort: a failure (timeout, parse error, model unavailable) on one chunk MUST NOT fail the ingest. Failures MUST increment `opencg_extractor_errors_total{reason}` and log a structured warning naming the chunk's `entity_id`.

Every extracted edge MUST carry a `confidence FLOAT`, an `evidence_uri TEXT` pointing at the source chunk's `entity_id`, and an `extractor_version TEXT`. Edges below a configurable `min_confidence` (default 0.6) MUST NOT be inserted at all.

#### Scenario: Extractor finds two new concepts and an edge in a chunk

- **WHEN** a newly upserted chunk's text mentions "Service A depends on Service B"
- **THEN** two `candidate` concept rows are created with `name` = `Service A` / `Service B` and normalised `dedupe_key`s
- **AND** a `candidate` edge is created with `type = "depends_on"`, `evidence_uri` referencing the chunk, and `confidence ≥ 0.6`

#### Scenario: Extractor reuses an existing concept

- **WHEN** a chunk mentions "Prompt Caching" and a concept with `dedupe_key = "prompt caching"` already exists
- **THEN** no new concept is created
- **AND** any new edge refers to the existing concept's `concept_id`

#### Scenario: Extractor failure does not fail the ingest

- **WHEN** the chat model is unreachable during a chunk's extraction pass
- **THEN** the chunk's catalog row and Qdrant point are still upserted
- **AND** `opencg_extractor_errors_total{reason}` increments
- **AND** no concept or edge rows are written for that chunk

#### Scenario: Edges below the confidence threshold are dropped

- **WHEN** the extractor returns an edge with `confidence = 0.3` and the configured `min_confidence` is `0.6`
- **THEN** no edge row is written for that triple
