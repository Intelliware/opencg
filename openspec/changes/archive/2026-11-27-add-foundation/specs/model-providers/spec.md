## ADDED Requirements

### Requirement: Provider-agnostic adapter interface

The system SHALL expose a single adapter interface per model capability — `EmbeddingProvider`, `IntentClassifier`, `Reranker`, `Generator` — and SHALL select the concrete implementation per capability via configuration. Switching providers SHALL NOT require pipeline code changes.

#### Scenario: Swap embedding provider via config

- **WHEN** the config value `embeddings.provider` is changed from `ollama` to `anthropic`
- **THEN** the next embedding call resolves the Anthropic implementation
- **AND** no pipeline-stage code is changed

### Requirement: Ollama adapter

The system SHALL ship an Ollama adapter implementing `EmbeddingProvider`, `IntentClassifier`, `Reranker`, and `Generator`. Adapter configuration SHALL include `base_url` and per-capability `model` name. The adapter SHALL stream tokens where the underlying model supports it.

#### Scenario: Ollama embedding call

- **WHEN** the embedding capability is configured with `provider = "ollama"`, `model = "nomic-embed-text"`
- **THEN** an embed call hits `POST <base_url>/api/embeddings` with the configured model and returns the embedding vector
- **AND** `tokens_in`, `latency_ms`, `model`, `provider` are recorded on the span

### Requirement: Anthropic adapter

The system SHALL ship an Anthropic adapter implementing `IntentClassifier` and `Generator`. The intent classifier adapter SHALL default to `claude-haiku-4-5` and SHALL include input/output token counts on the response.

#### Scenario: Anthropic intent classification

- **WHEN** the intent classifier is configured with `provider = "anthropic"`, `model = "claude-haiku-4-5"`
- **THEN** classification calls hit the Anthropic Messages API
- **AND** the response surfaces `usage.input_tokens` and `usage.output_tokens` to the pipeline accounting

### Requirement: OpenAI-compatible adapter

The system SHALL ship a generic OpenAI-compatible adapter (chat + embeddings endpoints) so deployments using vLLM, LM Studio, Azure OpenAI, or compatible OSS servers can be configured without writing new code.

#### Scenario: Configure vLLM-backed embeddings

- **WHEN** the embedding capability is configured with `provider = "openai_compatible"`, `base_url = "http://vllm:8000/v1"`, `model = "BAAI/bge-m3"`
- **THEN** embed calls hit `/v1/embeddings` and return vectors

### Requirement: Provider health checks

Each adapter SHALL expose a health probe used by the deployment health endpoints and the admin UI.

#### Scenario: Health probe

- **WHEN** the admin UI requests provider health
- **THEN** each configured provider is probed and the result (`ok` / `degraded` / `down`) is returned with latency
