## MODIFIED Requirements

### Requirement: ProviderConfig block

The `opencg.yaml` config SHALL gain a `providers` section with sub-blocks `embeddings` and `chat`. Each sub-block carries `provider`, `model`, `base_url`, and optional `api_key`. The existing `ollama` block stays for backwards compatibility (its values populate `providers.embeddings` if `providers.embeddings` is absent). Environment overrides MUST work via `OPENCG__PROVIDERS__CHAT__MODEL` etc.

`provider` is the label under which the endpoint's calls are counted, priced and traced. `ollama` and `ollama-cloud` both use the Ollama adapter. When `provider` is `ollama` and the `base_url` host is `ollama.com` or one of its subdomains, the endpoint MUST resolve to `provider=ollama-cloud`, and the service MUST log the resolution once at start-up.

#### Scenario: Defaults wire Cloud chat and local embeddings

- **WHEN** the project is cloned and only `.env.example` is copied to `.env`
- **THEN** `providers.embeddings` resolves to `provider=ollama, base_url=http://ollama:11434, model=nomic-embed-text, api_key=null`
- **AND** `providers.chat` resolves to `provider=ollama-cloud, base_url=https://ollama.com, model=gemma3:4b, api_key=<env-or-null>`

#### Scenario: Backwards compatibility with `ollama` block

- **WHEN** a deployment's `opencg.yaml` still has only the old `ollama:` block (no `providers:` section)
- **THEN** `providers.embeddings` is populated from `ollama.*`
- **AND** `providers.chat` falls back to `{provider:ollama, base_url:http://ollama:11434, model:gemma3:4b, api_key:null}` so existing local deployments keep working without Cloud

#### Scenario: Legacy Cloud label resolved

- **WHEN** a deployment's `providers.chat` has `provider: ollama` and `base_url: https://ollama.com`
- **THEN** the chat endpoint resolves to `provider=ollama-cloud`
- **AND** the service logs the resolution once

#### Scenario: Env override for chat model

- **WHEN** `OPENCG__PROVIDERS__CHAT__MODEL` is set to `kimi-k2`
- **THEN** the chat client uses `kimi-k2` regardless of the YAML value
