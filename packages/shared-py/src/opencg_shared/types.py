"""Wire types shared between Python services. Mirrors packages/shared/src/index.ts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IdentityContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    principal: str
    roles: tuple[str, ...]
    tenant: str


class RetrievalRequest(BaseModel):
    correlation_id: str
    identity: IdentityContext
    tool: str
    query: str
    top_k: int = 20
    token_budget: int = 4000
    filters: dict[str, Any] = Field(default_factory=dict)


class ContextFragment(BaseModel):
    entity_id: str
    source: str
    source_uri: str
    title: str | None = None
    text: str
    score: float
    tokens: int
    classification: str = "internal"


class StageUsage(BaseModel):
    stage: str
    model: str | None = None
    provider: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    # Estimated USD cost; None when the (provider, model) pair is unpriced
    # or the stage made no model call.
    cost_usd: float | None = None


class ProviderUsage(BaseModel):
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    # None means unpriced (no price entry), never "free".
    cost_usd: float | None = None


class UsageEnvelope(BaseModel):
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_latency_ms: int = 0
    by_stage: list[StageUsage] = Field(default_factory=list)
    by_provider: list[ProviderUsage] = Field(default_factory=list)
    # Sum of the priced entries in by_provider.
    estimated_cost_usd: float = 0.0
    # False when any by_provider entry is unpriced.
    cost_complete: bool = True


def summarise_by_provider(stages: list[StageUsage]) -> tuple[list[ProviderUsage], float, bool]:
    """Fold model-calling stages into one entry per (provider, model).

    Returns (by_provider, estimated_cost_usd, cost_complete). Stages without a
    provider and model (no model call) are skipped.
    """
    order: list[tuple[str, str]] = []
    acc: dict[tuple[str, str], ProviderUsage] = {}
    unpriced: set[tuple[str, str]] = set()
    for st in stages:
        if not st.provider or not st.model:
            continue
        key = (st.provider, st.model)
        if key not in acc:
            order.append(key)
            acc[key] = ProviderUsage(provider=st.provider, model=st.model, cost_usd=0.0)
        entry = acc[key]
        entry.tokens_in += st.tokens_in
        entry.tokens_out += st.tokens_out
        if st.cost_usd is None:
            unpriced.add(key)
        else:
            entry.cost_usd = (entry.cost_usd or 0.0) + st.cost_usd
    for key in unpriced:
        acc[key].cost_usd = None
    by_provider = [acc[k] for k in order]
    for entry in by_provider:
        if entry.cost_usd is not None:
            entry.cost_usd = round(entry.cost_usd, 6)
    total = round(sum(e.cost_usd for e in by_provider if e.cost_usd is not None), 6)
    return by_provider, total, not unpriced


class RetrievalResponse(BaseModel):
    correlation_id: str
    fragments: list[ContextFragment]
    usage: UsageEnvelope
    final_context_hash: str
    vector_collection: str | None = None
    vector_snapshot_id: str | None = None


class AuditRecord(BaseModel):
    id: int
    created_at: datetime
    correlation_id: str
    tenant: str
    principal: str
    roles: list[str]
    tool: str
    query: str
    candidate_ids: list[str]
    final_entity_ids: list[str]
    final_context_hash: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    outcome: Literal["ok", "error"]
    error_code: str | None = None
    # Null on rows written before cost was recorded.
    estimated_cost_usd: float | None = None
    usage_by_provider: list[ProviderUsage] | None = None


class IngestEvent(BaseModel):
    type: Literal["document_created", "document_updated", "document_tombstoned"]
    tenant: str
    entity_id: str
    source: str
    source_uri: str
    content_hash: str


# --- Admin: catalog read ---------------------------------------------------


class EntityListItem(BaseModel):
    entity_id: str
    tenant: str
    source: str
    source_uri: str
    title: str | None = None
    classification: str
    freshness_state: str
    updated_at: datetime
    tombstoned_at: datetime | None = None


class EntityRef(BaseModel):
    entity_id: str
    title: str | None = None
    source_uri: str


class EntityLineage(BaseModel):
    parent: EntityRef | None = None
    children: list[EntityRef] = Field(default_factory=list)


class EntityAuditAppearance(BaseModel):
    id: int
    created_at: datetime
    correlation_id: str
    tool: str
    query: str
    outcome: Literal["ok", "error"]


class Entity(EntityListItem):
    body: str
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_revision: str | None = None
    parent_entity_id: str | None = None
    created_at: datetime
    ingested_at: datetime
    last_verified_at: datetime
    lineage: EntityLineage = Field(default_factory=EntityLineage)
    audit_appearances: list[EntityAuditAppearance] = Field(default_factory=list)


class EntityListResponse(BaseModel):
    items: list[EntityListItem]
    total: int
    limit: int
    offset: int


# --- Admin: vector search --------------------------------------------------


class VectorSearchHit(BaseModel):
    entity_id: str
    score: float
    source: str
    source_uri: str
    title: str | None = None
    classification: str = "internal"
    snippet: str
    collection: str | None = None


class VectorSearchResponse(BaseModel):
    hits: list[VectorSearchHit]
    model: str
    provider: str
    tokens_in: int
    # Estimated USD cost of the query embedding; None when unpriced.
    cost_usd: float | None = None
    usage: UsageEnvelope | None = None


# --- Admin: ingestion ------------------------------------------------------


class ConnectorStatus(BaseModel):
    name: str
    supported: bool
    reason: str | None = None


IngestionRunStatus = Literal["queued", "running", "succeeded", "failed"]


class IngestionRun(BaseModel):
    run_id: str
    connector: str
    repo: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: IngestionRunStatus
    parents: int | None = None
    chunks: int | None = None
    error: str | None = None


# --- Knowledge graph ------------------------------------------------------


EdgeState = Literal["candidate", "confirmed", "tombstoned"]


class RelationshipType(BaseModel):
    name: str
    description: str
    inverse: str | None = None
    directed: bool = True
    deprecated_at: datetime | None = None


class ConceptListItem(BaseModel):
    concept_id: str
    tenant: str
    name: str
    state: EdgeState
    confidence: float | None = None
    aliases: list[str] = Field(default_factory=list)
    symbol_id: str | None = None
    symbol_kind: str | None = None
    updated_at: datetime
    tombstoned_at: datetime | None = None


class Concept(ConceptListItem):
    dedupe_key: str
    description: str | None = None
    extractor_version: str | None = None
    source_entity_id: str | None = None
    created_at: datetime


class RelationshipEdge(BaseModel):
    edge_id: str
    tenant: str
    type: str
    from_concept_id: str
    to_concept_id: str
    state: EdgeState
    confidence: float
    extractor_version: str | None = None
    created_at: datetime
    updated_at: datetime
    tombstoned_at: datetime | None = None


class Neighbour(BaseModel):
    edge: RelationshipEdge
    peer: ConceptListItem
    evidence_entity_ids: list[str] = Field(default_factory=list)


class ConceptDetail(Concept):
    neighbours_confirmed: list[Neighbour] = Field(default_factory=list)
    neighbours_candidate: list[Neighbour] = Field(default_factory=list)


class TraverseRequest(BaseModel):
    concept_id: str
    types: list[str] | None = None
    depth: int = 2
    limit: int = 50
    include_candidates: bool = False


class TraverseResponse(BaseModel):
    nodes: list[ConceptListItem] = Field(default_factory=list)
    edges: list[RelationshipEdge] = Field(default_factory=list)


class ExtractedConcept(BaseModel):
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)


class ExtractedRelation(BaseModel):
    from_: str = Field(alias="from")
    relation: str
    to: str
    evidence_span: str | None = None
    confidence: float

    model_config = ConfigDict(populate_by_name=True)


class ExtractionResult(BaseModel):
    concepts: list[ExtractedConcept] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


class GraphAuditRow(BaseModel):
    id: int
    created_at: datetime
    actor: str
    tenant: str
    target_kind: Literal["concept", "edge", "vocab"]
    target_id: str
    from_state: str | None = None
    to_state: str | None = None
    reason: str | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
