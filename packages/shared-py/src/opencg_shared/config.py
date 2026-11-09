"""Config loader. YAML file + OPENCG__SECTION__KEY env overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class IdentityCfg(BaseModel):
    principal: str = "local-dev"
    roles: list[str] = Field(default_factory=lambda: ["admin", "reader"])


class PostgresCfg(BaseModel):
    url: str = "postgresql://opencg:opencg@postgres:5432/opencg"


class QdrantCfg(BaseModel):
    url: str = "http://qdrant:6333"
    collection_prefix: str = "default__"
    vector_size: int = 768
    distance: str = "cosine"


class ValkeyCfg(BaseModel):
    url: str = "redis://valkey:6379/0"


class OllamaCfg(BaseModel):
    base_url: str = "https://ollama.com"
    embedding_model: str = "nomic-embed-text"
    api_key: str | None = None


# --- Providers --------------------------------------------------------------
# The thin MVP had one model caller (embeddings). With add-knowledge-graph
# adding an LLM extractor for non-code chunks, we now have two. A small
# per-capability config block keeps each caller pointable at a different
# host/model/key without growing a full provider abstraction yet.


class ProviderEndpoint(BaseModel):
    """One model caller's wire config."""

    provider: str = "ollama"
    base_url: str
    model: str
    api_key: str | None = None


class ExtractionCfg(BaseModel):
    """Knobs for the LLM-based text extractor."""

    enabled: bool = True
    min_confidence: float = 0.6
    timeout_seconds: float = 30.0
    chat_qps: float | None = None  # null = unbounded


class ProvidersCfg(BaseModel):
    embeddings: ProviderEndpoint | None = None
    chat: ProviderEndpoint | None = None
    extraction: ExtractionCfg = Field(default_factory=ExtractionCfg)


class RetrievalCfg(BaseModel):
    default_top_k: int = 20
    default_token_budget: int = 4000
    tokens_per_char: float = 0.25


class AuditCfg(BaseModel):
    retention_days: int = 90


class TelemetryCfg(BaseModel):
    otlp_endpoint: str = "http://otel-collector:4318"
    service_namespace: str = "opencg"


class IngestionGitCfg(BaseModel):
    repos: list[str] = Field(default_factory=list)
    # Guards for URLs submitted over the HTTP API (admin UI "Run now").
    # allowed_hosts: hosts that may resolve to private addresses (internal git).
    # local_roots: directories local repo paths may live under (empty = none).
    allowed_hosts: list[str] = Field(default_factory=list)
    local_roots: list[str] = Field(default_factory=list)

    @field_validator("allowed_hosts", "local_roots", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class IngestionCfg(BaseModel):
    git: IngestionGitCfg = Field(default_factory=IngestionGitCfg)


class openCGConfig(BaseModel):
    tenant: str = "default"
    identity: IdentityCfg = Field(default_factory=IdentityCfg)
    postgres: PostgresCfg = Field(default_factory=PostgresCfg)
    qdrant: QdrantCfg = Field(default_factory=QdrantCfg)
    valkey: ValkeyCfg = Field(default_factory=ValkeyCfg)
    ollama: OllamaCfg = Field(default_factory=OllamaCfg)
    providers: ProvidersCfg = Field(default_factory=ProvidersCfg)
    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)
    audit: AuditCfg = Field(default_factory=AuditCfg)
    telemetry: TelemetryCfg = Field(default_factory=TelemetryCfg)
    ingestion: IngestionCfg = Field(default_factory=IngestionCfg)

    def model_post_init(self, _ctx: Any) -> None:
        # Back-compat: if `providers.embeddings` is unset, derive it from
        # the legacy `ollama` block so existing deployments don't need a
        # config rewrite. The reverse — populating `providers` THEN reading
        # `ollama` — is also fine because `ollama` keeps its own fields.
        if self.providers.embeddings is None:
            self.providers.embeddings = ProviderEndpoint(
                provider="ollama",
                base_url=self.ollama.base_url,
                model=self.ollama.embedding_model,
                api_key=self.ollama.api_key,
            )
        if self.providers.chat is None:
            # Backwards-compatible deployments that only have the legacy
            # Ollama block remain local. The checked-in YAML explicitly opts
            # new deployments into Ollama Cloud chat.
            self.providers.chat = ProviderEndpoint(
                provider="ollama",
                base_url=self.ollama.base_url,
                model="gemma3:4b",
                api_key=None,
            )


_ENV_PREFIX = "OPENCG__"


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply OPENCG__SECTION__KEY env vars onto a nested dict."""
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        path = [seg.lower() for seg in key[len(_ENV_PREFIX) :].split("__")]
        cur = data
        for seg in path[:-1]:
            cur = cur.setdefault(seg, {})
            if not isinstance(cur, dict):
                # Conflict: a leaf value where a section is expected. Skip.
                break
        else:
            leaf = path[-1]
            # Comma-separated list support for roles[]/repos[].
            if "," in value and leaf in ("roles", "repos"):
                cur[leaf] = [v.strip() for v in value.split(",") if v.strip()]
            else:
                cur[leaf] = value
    return data


def load_config(path: str | Path | None = None) -> openCGConfig:
    """Load YAML (if present) then layer env-var overrides on top."""
    raw: dict[str, Any] = {}
    if path is None:
        path = os.environ.get("OPENCG_CONFIG", "opencg.yaml")
    p = Path(path)
    if p.is_file():
        raw = yaml.safe_load(p.read_text()) or {}
    raw = _apply_env_overrides(raw)
    return openCGConfig.model_validate(raw)
