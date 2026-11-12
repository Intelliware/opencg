"""Knowledge graph read and administration HTTP routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query, Request
from opencg_shared import (
    ConceptDetail,
    ConceptListItem,
    TraverseResponse,
    extract_context,
    stage_span,
)
from opencg_shared.metrics import observe_stage
from pydantic import BaseModel, Field

router = APIRouter(prefix="/graph", tags=["graph"])

_VALID_STATES = {"candidate", "confirmed", "tombstoned"}


class ReasonBody(BaseModel):
    reason: str | None = None


class ConceptPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    aliases: list[str] | None = None
    reason: str | None = None


class EdgePatch(BaseModel):
    type: str | None = None
    from_concept_id: str | None = None
    to_concept_id: str | None = None
    reason: str | None = None


class VocabCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    inverse: str | None = None
    directed: bool = True


class VocabPatch(BaseModel):
    description: str | None = None
    inverse: str | None = None
    directed: bool | None = None


class ConceptMerge(BaseModel):
    into_id: str
    from_ids: list[str] = Field(min_length=1)
    reason: str | None = None


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@router.get("/vocab")
async def list_vocabulary(request: Request) -> dict:
    return {"items": await request.app.state.graph.list_vocabulary()}


@router.get("/concepts")
async def list_concepts(
    request: Request,
    state: str = "confirmed,candidate",
    search: str | None = None,
    include_tombstoned: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    states = _csv(state)
    if any(item not in _VALID_STATES for item in states):
        raise HTTPException(status_code=400, detail="invalid concept state")
    rows, total = await request.app.state.graph.list_concepts(
        tenant=request.app.state.cfg.tenant,
        states=states,
        search=search,
        include_tombstoned=include_tombstoned,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [ConceptListItem.model_validate(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/concepts/{concept_id}", response_model=ConceptDetail)
async def get_concept(request: Request, concept_id: str) -> ConceptDetail:
    row = await request.app.state.graph.get_concept(
        tenant=request.app.state.cfg.tenant,
        concept_id=concept_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="concept not found")
    return ConceptDetail.model_validate(row)


@router.get("/edges")
async def list_edges(
    request: Request,
    state: str | None = None,
    type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    if state is not None and state not in _VALID_STATES:
        raise HTTPException(status_code=400, detail="invalid edge state")
    rows, total = await request.app.state.graph.list_edges(
        tenant=request.app.state.cfg.tenant,
        state=state,
        relationship_type=type,
        limit=limit,
        offset=offset,
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/traverse", response_model=TraverseResponse)
async def traverse(
    request: Request,
    concept_id: str,
    types: str | None = None,
    depth: int = Query(default=2, ge=1, le=4),
    limit: int = Query(default=50, ge=1, le=200),
    include_candidates: bool = False,
) -> TraverseResponse:
    # The MCP server sends W3C traceparent plus x-correlation-id (no body here).
    tracer = getattr(request.app.state, "tracer", None)
    t0 = time.perf_counter()
    try:
        if tracer is None:
            result = await _run_traverse(
                request, concept_id, types, depth, limit, include_candidates
            )
        else:
            with stage_span(
                tracer,
                "pipeline.graph_traverse",
                request.headers.get("x-correlation-id"),
                context=extract_context(request.headers),
                concept_id=concept_id,
                depth=depth,
            ):
                result = await _run_traverse(
                    request, concept_id, types, depth, limit, include_candidates
                )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "concept_not_found", "concept_id": concept_id},
        )
    observe_stage("graph_traverse", time.perf_counter() - t0)
    return TraverseResponse.model_validate(result)


async def _run_traverse(request, concept_id, types, depth, limit, include_candidates):
    return await request.app.state.graph.traverse(
        tenant=request.app.state.cfg.tenant,
        concept_id=concept_id,
        types=_csv(types) or None,
        depth=depth,
        limit=limit,
        include_candidates=include_candidates,
    )


async def _transition_concept(
    request: Request, concept_id: str, state: str, body: ReasonBody | None
) -> dict:
    cfg = request.app.state.cfg
    row = await request.app.state.graph.transition_concept(
        tenant=cfg.tenant,
        concept_id=concept_id,
        state=state,
        actor=cfg.identity.principal,
        reason=body.reason if body else None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="concept not found")
    return row


@router.post("/concepts/{concept_id}/promote")
async def promote_concept(
    request: Request, concept_id: str, body: ReasonBody | None = None
) -> dict:
    return await _transition_concept(request, concept_id, "confirmed", body)


@router.post("/concepts/{concept_id}/demote")
async def demote_concept(request: Request, concept_id: str, body: ReasonBody | None = None) -> dict:
    return await _transition_concept(request, concept_id, "candidate", body)


@router.delete("/concepts/{concept_id}")
async def tombstone_concept(
    request: Request, concept_id: str, body: ReasonBody | None = None
) -> dict:
    return await _transition_concept(request, concept_id, "tombstoned", body)


@router.patch("/concepts/{concept_id}")
async def patch_concept(request: Request, concept_id: str, body: ConceptPatch) -> dict:
    cfg = request.app.state.cfg
    try:
        row = await request.app.state.graph.patch_concept(
            tenant=cfg.tenant,
            concept_id=concept_id,
            actor=cfg.identity.principal,
            reason=body.reason,
            changes=body.model_dump(exclude_none=True, exclude={"reason"}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="concept not found")
    return row


@router.post("/concepts/merge")
async def merge_concepts(request: Request, body: ConceptMerge) -> dict:
    cfg = request.app.state.cfg
    try:
        row = await request.app.state.graph.merge_concepts(
            tenant=cfg.tenant,
            into_id=body.into_id,
            from_ids=body.from_ids,
            actor=cfg.identity.principal,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="merge target not found")
    return row


async def _transition_edge(
    request: Request, edge_id: str, state: str, body: ReasonBody | None
) -> dict:
    cfg = request.app.state.cfg
    row = await request.app.state.graph.transition_edge(
        tenant=cfg.tenant,
        edge_id=edge_id,
        state=state,
        actor=cfg.identity.principal,
        reason=body.reason if body else None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="edge not found")
    return row


@router.post("/edges/{edge_id}/promote")
async def promote_edge(request: Request, edge_id: str, body: ReasonBody | None = None) -> dict:
    return await _transition_edge(request, edge_id, "confirmed", body)


@router.post("/edges/{edge_id}/demote")
async def demote_edge(request: Request, edge_id: str, body: ReasonBody | None = None) -> dict:
    return await _transition_edge(request, edge_id, "candidate", body)


@router.delete("/edges/{edge_id}")
async def tombstone_edge(request: Request, edge_id: str, body: ReasonBody | None = None) -> dict:
    return await _transition_edge(request, edge_id, "tombstoned", body)


@router.patch("/edges/{edge_id}")
async def patch_edge(request: Request, edge_id: str, body: EdgePatch) -> dict:
    cfg = request.app.state.cfg
    try:
        row = await request.app.state.graph.patch_edge(
            tenant=cfg.tenant,
            edge_id=edge_id,
            actor=cfg.identity.principal,
            reason=body.reason,
            changes=body.model_dump(exclude_none=True, exclude={"reason"}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="edge not found")
    return row


@router.post("/vocab", status_code=201)
async def create_vocabulary(request: Request, body: VocabCreate) -> dict:
    cfg = request.app.state.cfg
    try:
        return await request.app.state.graph.create_vocabulary(
            tenant=cfg.tenant,
            actor=cfg.identity.principal,
            data=body.model_dump(),
        )
    except ValueError as exc:
        status = 409 if str(exc) == "vocab_name_in_use" else 400
        raise HTTPException(
            status_code=status,
            detail={"code": str(exc)},
        ) from exc


@router.patch("/vocab/{name}")
async def patch_vocabulary(request: Request, name: str, body: VocabPatch) -> dict:
    cfg = request.app.state.cfg
    row = await request.app.state.graph.patch_vocabulary(
        tenant=cfg.tenant,
        name=name,
        actor=cfg.identity.principal,
        changes=body.model_dump(exclude_none=True),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="vocabulary entry not found")
    return row


@router.post("/vocab/{name}/deprecate")
async def deprecate_vocabulary(request: Request, name: str, body: ReasonBody | None = None) -> dict:
    cfg = request.app.state.cfg
    row = await request.app.state.graph.deprecate_vocabulary(
        tenant=cfg.tenant,
        name=name,
        actor=cfg.identity.principal,
        reason=body.reason if body else None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="vocabulary entry not found")
    return row
