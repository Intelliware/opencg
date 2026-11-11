## MODIFIED Requirements

### Requirement: Provider-agnostic adapter interface

In v0 the pipeline SHALL call a single concrete `OllamaEmbeddings` client. The protocol abstractions (`EmbeddingProvider`, `IntentClassifier`, `Reranker`, `Generator`) MUST be introduced by the follow-up change that adds the second model caller (intent classifier or generator), at which point this requirement is re-modified.

#### Scenario: Single concrete embeddings client in v0

- **WHEN** the pipeline service starts in the thin MVP
- **THEN** exactly one model client is instantiated and it is the Ollama-compatible embeddings client

### Requirement: Ollama adapter

The Ollama adapter SHALL implement embeddings against an Ollama-compatible HTTP endpoint configured via `base_url` and `model`. The adapter MUST support both the legacy `/api/embeddings` request/response shape (`{"prompt":"…"}` → `{"embedding":[...]}`) and the newer `/api/embed` shape (`{"input":"…"}` → `{"embeddings":[[...]]}`).

In v0 the adapter MUST implement embeddings only; intent classification, reranking, and generation methods are deferred.

#### Scenario: Embed against a local Ollama daemon

- **WHEN** the embeddings client is configured with `base_url = "http://ollama:11434"`, `model = "nomic-embed-text"` and `api_key = null`
- **THEN** an embed call hits the configured base URL and returns a vector
- **AND** the request omits the `Authorization` header

#### Scenario: Embed against an Ollama-compatible endpoint with an API key

- **WHEN** the embeddings client is configured with a non-empty `api_key`
- **THEN** every outbound request includes `Authorization: Bearer <key>`
- **AND** the existing request body shape is unchanged

### Requirement: Anthropic adapter

The system SHALL NOT include an Anthropic adapter in v0. A follow-up change MUST add it together with the first caller (intent classifier or generator). No Anthropic env var MAY be required to bring up v0.

#### Scenario: Anthropic adapter is absent in v0

- **WHEN** the pipeline service starts in the thin MVP
- **THEN** no Anthropic client is instantiated and no Anthropic env var is required

### Requirement: OpenAI-compatible adapter

The system SHALL NOT include an OpenAI-compatible adapter in v0. A follow-up change MUST add it once a second model capability is wired through the abstraction.

#### Scenario: OpenAI-compatible adapter is absent in v0

- **WHEN** the pipeline service starts in the thin MVP
- **THEN** no OpenAI-compatible client is instantiated

### Requirement: Provider health checks

In v0 the pipeline's `/readyz` endpoint SHALL be the only required health probe for the embeddings backend; an explicit per-provider probe page in the admin UI is deferred.

#### Scenario: Pipeline readiness covers the embeddings backend in v0

- **WHEN** the pipeline's `/readyz` endpoint is hit and the embeddings backend is reachable
- **THEN** the endpoint returns `200`

## ADDED Requirements

### Requirement: Ollama Cloud is not a viable embeddings backend in v0

The system SHALL document that Ollama Cloud's `/api/embed` endpoint is gated and unavailable on the project's reference account as of 2026-06-11. Thin-MVP deployments MUST default the embeddings `base_url` to a local Ollama-compatible service.

#### Scenario: Default embeddings base URL targets local Ollama

- **WHEN** the project is cloned and no env overrides are set
- **THEN** `OPENCG__OLLAMA__BASE_URL` resolves to `http://ollama:11434`
- **AND** the configured embedding model is one supported by the local Ollama image

#### Scenario: Cloud env keys remain configurable but unused by v0

- **WHEN** `OPENCG__OLLAMA__API_KEY` is set in the environment
- **THEN** the embeddings client adds an `Authorization: Bearer <key>` header to outbound requests
- **AND** no automated v0 behaviour requires the key to be present
