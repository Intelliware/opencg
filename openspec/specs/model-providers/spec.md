# model-providers Specification

## Purpose

Give every model call (embeddings and chat) a provider-agnostic adapter, configured per purpose, with Ollama as the default backend for both local and hosted models.

## Requirements
### Requirement: Provider-agnostic adapter interface

The full protocol abstraction (`EmbeddingProvider` / `IntentClassifier` / `Reranker` / `Generator`) described in `add-foundation/specs/model-providers/spec.md` REMAINS deferred. This change ships a second concrete client (`OllamaChat`) alongside the existing `OllamaEmbeddings`. A single shared `ProviderConfig` SHALL select per-capability `(provider, model, base_url, api_key)` for each model caller. The provider-protocol abstraction is introduced when a third caller (e.g., rerank or intent classification) lands.

#### Scenario: Two concrete model clients in this change

- **WHEN** the pipeline + ingestion services start
- **THEN** `OllamaEmbeddings` and `OllamaChat` are instantiated from the same `providers` config block
- **AND** no protocol abstraction exists

### Requirement: Ollama adapter

The Ollama adapter SHALL implement embeddings (as before, against `/api/embed` with fallback to `/api/embeddings`) AND chat (against `/api/chat` with `{model, messages, stream:false}`, response `{message:{role,content}, eval_count?, prompt_eval_count?}`). Both flavours MUST support `Authorization: Bearer <key>` when the per-capability `api_key` is set.

The chat client MUST:
- Send `format = "json"` whenever a `response_schema` is provided so the chat model returns parseable JSON.
- Surface `prompt_eval_count` as `tokens_in` and `eval_count` as `tokens_out` on the response object so callers can attribute usage to the right counter.
- Raise on any non-200 response.

#### Scenario: Chat against Ollama Cloud with the configured key

- **WHEN** the chat client is configured with `base_url = "https://ollama.com"`, `model = "gemma3:4b"`, `api_key = "…"`
- **THEN** outbound requests hit `POST https://ollama.com/api/chat` with `Authorization: Bearer …`
- **AND** the response's `tokens_in` / `tokens_out` are populated from `prompt_eval_count` / `eval_count`

#### Scenario: Chat against a local Ollama daemon

- **WHEN** the chat client is configured with `base_url = "http://ollama:11434"` and `api_key = null`
- **THEN** outbound requests omit the Authorization header

#### Scenario: Format=json is requested when a response_schema is supplied

- **WHEN** the extractor calls the chat client with a `response_schema`
- **THEN** the outbound JSON body contains `"format": "json"`
- **AND** the response is parsed as JSON before being returned

### Requirement: ProviderConfig block

The `opencg.yaml` config SHALL gain a `providers` section with sub-blocks `embeddings` and `chat`. Each sub-block carries `provider`, `model`, `base_url`, and optional `api_key`. The existing `ollama` block stays for backwards compatibility (its values populate `providers.embeddings` if `providers.embeddings` is absent). Environment overrides MUST work via `OPENCG__PROVIDERS__CHAT__MODEL` etc.

#### Scenario: Defaults wire Cloud chat and local embeddings

- **WHEN** the project is cloned and only `.env.example` is copied to `.env`
- **THEN** `providers.embeddings` resolves to `provider=ollama, base_url=http://ollama:11434, model=nomic-embed-text, api_key=null`
- **AND** `providers.chat` resolves to `provider=ollama, base_url=https://ollama.com, model=gemma3:4b, api_key=<env-or-null>`

#### Scenario: Backwards compatibility with `ollama` block

- **WHEN** a deployment's `opencg.yaml` still has only the old `ollama:` block (no `providers:` section)
- **THEN** `providers.embeddings` is populated from `ollama.*`
- **AND** `providers.chat` falls back to `{provider:ollama, base_url:http://ollama:11434, model:gemma3:4b, api_key:null}` so existing local deployments keep working without Cloud

#### Scenario: Env override for chat model

- **WHEN** `OPENCG__PROVIDERS__CHAT__MODEL` is set to `kimi-k2`
- **THEN** the chat client uses `kimi-k2` regardless of the YAML value
