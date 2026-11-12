"""Admin-side HTTP endpoints for the pipeline service.

These power the admin UI (`/vectors`, `/entities`, `/ingestion`). They are
read-mostly: entity list/detail are pure reads, tombstone is a soft-delete,
vector search uses the same embeddings client the retrieve path uses but
writes no audit row, and the ingestion endpoints are thin proxies to the
ingestion service over the compose network.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from opencg_shared import (
    Entity,
    EntityAuditAppearance,
    EntityLineage,
    EntityListItem,
    EntityListResponse,
    EntityRef,
    StageUsage,
    UsageEnvelope,
    VectorSearchHit,
    VectorSearchResponse,
    extract_context,
    record_stage_tokens,
    summarise_by_provider,
)
from opencg_shared.metrics import observe_stage
from pydantic import BaseModel, Field

from opencg_pipeline.stages.hybrid_retrieval import drop_tombstoned, overfetch_limit

router = APIRouter()

_VECTOR_TOP_K_CAP = 100
_SNIPPET_CHARS = 280


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=20, ge=1, le=_VECTOR_TOP_K_CAP)
    filters: dict[str, Any] | None = None


def _snippet(text: str | None) -> str:
    if not text:
        return ""
    s = text.strip().replace("\n", " ").replace("\r", " ")
    return s[:_SNIPPET_CHARS] + ("…" if len(s) > _SNIPPET_CHARS else "")


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    request: Request,
    source: str | None = Query(default=None),
    classification: str | None = Query(default=None),
    freshness_state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EntityListResponse:
    cfg = request.app.state.cfg
    rows, total = await request.app.state.catalog.list_entities(
        tenant=cfg.tenant,
        source=source,
        classification=classification,
        freshness_state=freshness_state,
        limit=limit,
        offset=offset,
    )
    items = [EntityListItem.model_validate(r) for r in rows]
    return EntityListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/entities/{entity_id}", response_model=Entity)
async def get_entity(request: Request, entity_id: str) -> Entity:
    cfg = request.app.state.cfg
    row = await request.app.state.catalog.get_entity_with_lineage(
        tenant=cfg.tenant, entity_id=entity_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    # Normalise lineage children into EntityRef-shaped dicts the Pydantic model
    # can consume directly.
    lineage_in = row.get("lineage") or {}
    lineage = EntityLineage(
        parent=EntityRef.model_validate(lineage_in["parent"]) if lineage_in.get("parent") else None,
        children=[EntityRef.model_validate(c) for c in lineage_in.get("children", [])],
    )
    row["lineage"] = lineage.model_dump()
    appearances = await request.app.state.audit.list_for_entity(
        tenant=cfg.tenant, entity_id=entity_id, limit=20
    )
    row["audit_appearances"] = [
        EntityAuditAppearance.model_validate(item).model_dump() for item in appearances
    ]
    return Entity.model_validate(row)


@router.delete("/entities/{entity_id}", response_model=EntityListItem)
async def tombstone_entity(request: Request, entity_id: str) -> EntityListItem:
    cfg = request.app.state.cfg
    row = await request.app.state.catalog.tombstone(tenant=cfg.tenant, entity_id=entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return EntityListItem.model_validate(row)


@router.post("/search/vector", response_model=VectorSearchResponse)
async def vector_search(request: Request, payload: VectorSearchRequest) -> VectorSearchResponse:
    embeddings = request.app.state.embeddings
    vector_index = request.app.state.vector
    tracer = request.app.state.tracer
    cfg = request.app.state.cfg
    correlation_id = request.headers.get("x-correlation-id") or f"vector-{uuid.uuid4()}"

    with tracer.start_as_current_span(
        "pipeline.vector_search", context=extract_context(request.headers)
    ) as span:
        span.set_attribute("correlation_id", correlation_id)
        t0 = time.perf_counter()
        emb = await embeddings.embed(payload.query)
        hits = await vector_index.search_all(
            vector=emb.vector, limit=overfetch_limit(payload.top_k), filters=payload.filters
        )
        hits, tombstoned_filtered = await drop_tombstoned(
            hits, catalog=request.app.state.catalog, tenant=cfg.tenant, limit=payload.top_k
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        span.set_attribute("model", emb.model)
        span.set_attribute("provider", emb.provider)
        span.set_attribute("tokens_in", emb.tokens_in)
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("hits", len(hits))
        span.set_attribute("tombstoned_filtered", tombstoned_filtered)
    observe_stage("vector_search", time.perf_counter() - t0)

    cost = record_stage_tokens(
        stage="vector_search",
        tenant=cfg.tenant,
        tokens_in=emb.tokens_in,
        tokens_out=0,
        model=emb.model,
        provider=emb.provider,
    )

    stages = [
        StageUsage(
            stage="vector_search",
            model=emb.model,
            provider=emb.provider,
            tokens_in=emb.tokens_in,
            latency_ms=latency_ms,
            cost_usd=cost,
        )
    ]
    by_provider, estimated, complete = summarise_by_provider(stages)

    return VectorSearchResponse(
        hits=[
            VectorSearchHit(
                entity_id=h.entity_id,
                score=h.score,
                source=str(h.payload.get("source", "")),
                source_uri=str(h.payload.get("source_uri", "")),
                title=h.payload.get("title"),
                classification=str(h.payload.get("classification", "internal")),
                snippet=_snippet(h.payload.get("text")),
                collection=h.collection,
            )
            for h in hits
        ],
        model=emb.model,
        provider=emb.provider,
        tokens_in=emb.tokens_in,
        cost_usd=cost,
        usage=UsageEnvelope(
            total_tokens_in=emb.tokens_in,
            total_latency_ms=latency_ms,
            by_stage=stages,
            by_provider=by_provider,
            estimated_cost_usd=estimated,
            cost_complete=complete,
        ),
    )


# --- Ingestion proxies -----------------------------------------------------


async def _proxy(request: Request, method: str, path: str, json: Any | None = None) -> Any:
    client: httpx.AsyncClient = request.app.state.ingestion_client
    try:
        resp = await client.request(method, path, json=json)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail={"upstream": "unreachable", "error": str(exc)}
        ) from exc
    if resp.status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail={"upstream_status": resp.status_code, "body": resp.text[:2000]},
        )
    if resp.status_code >= 400:
        # Forward 4xx (e.g. bad request from caller) as-is.
        raise HTTPException(status_code=resp.status_code, detail=resp.json())
    return resp.json()


@router.get("/ingestion/connectors")
async def proxy_connectors(request: Request) -> Any:
    return await _proxy(request, "GET", "/connectors")


@router.post("/ingestion/git/run")
async def proxy_run_git(request: Request, body: dict[str, Any]) -> Any:
    return await _proxy(request, "POST", "/run/git", json=body)


@router.get("/ingestion/runs/recent")
async def proxy_runs_recent(request: Request) -> Any:
    return await _proxy(request, "GET", "/runs/recent")
