"""FastAPI app — the retrieval pipeline."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opencg_shared import (
    ContextFragment,
    RetrievalRequest,
    RetrievalResponse,
    StageUsage,
    UsageEnvelope,
    extract_context,
    load_config,
    metrics_app,
    openCGConfig,
    record_request,
    record_stage_tokens,
    setup_otel,
    stage_span,
    summarise_by_provider,
)
from opencg_shared.metrics import observe_stage
from opencg_shared.otel import CORRELATION_HEADER, tag_request_span
from opentelemetry import trace
from starlette.routing import Route

from opencg_pipeline import admin_routes
from opencg_pipeline.graph import routes as graph_routes
from opencg_pipeline.providers import OllamaEmbeddings
from opencg_pipeline.stages import assemble, hybrid_retrieval, identity
from opencg_pipeline.storage.audit import AuditStore
from opencg_pipeline.storage.catalog import CatalogStore
from opencg_pipeline.storage.graph import GraphStore
from opencg_pipeline.storage.vector import VectorIndex
from opencg_pipeline.util import estimate_tokens, hash_context

log = logging.getLogger(__name__)

_VERSION = "0.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    tracer = setup_otel(
        "opencg-pipeline",
        cfg.telemetry.service_namespace,
        config_endpoint=cfg.telemetry.otlp_endpoint,
    )
    catalog = CatalogStore(cfg.postgres.url)
    audit = AuditStore(cfg.postgres.url)
    graph = GraphStore(cfg.postgres.url)
    vector = VectorIndex(
        url=cfg.qdrant.url,
        collection_prefix=cfg.qdrant.collection_prefix,
        vector_size=cfg.qdrant.vector_size,
        distance=cfg.qdrant.distance,
    )
    embeddings = OllamaEmbeddings(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embedding_model,
        api_key=cfg.ollama.api_key,
        provider=cfg.embeddings_endpoint().provider,
    )
    ingestion_url = os.environ.get("OPENCG__INGESTION__URL", "http://ingestion:8100")
    ingestion_client = httpx.AsyncClient(base_url=ingestion_url, timeout=30.0)
    await catalog.connect()
    await audit.connect()
    await graph.connect()
    app.state.cfg = cfg
    app.state.tracer = tracer
    app.state.catalog = catalog
    app.state.audit = audit
    app.state.graph = graph
    app.state.vector = vector
    app.state.embeddings = embeddings
    app.state.ingestion_client = ingestion_client
    try:
        yield
    finally:
        await catalog.close()
        await audit.close()
        await graph.close()
        await vector.close()
        await embeddings.close()
        await ingestion_client.aclose()


app = FastAPI(title="opencg-pipeline", lifespan=lifespan)
app.router.routes.append(Route("/metrics", metrics_app))


@app.middleware("http")
async def _tag_correlation_id(request: Request, call_next):
    # FastAPI traces each request itself; tag its span so it (and, through
    # CorrelationIdSpanProcessor, its children) carry the caller's ID.
    tag_request_span(request.headers.get(CORRELATION_HEADER))
    return await call_next(request)


app.include_router(admin_routes.router)
app.include_router(graph_routes.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    cfg: openCGConfig = app.state.cfg
    # Touch each backend cheaply. Errors surface as 503.
    try:
        async with app.state.catalog._require_pool().acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres: {exc}") from exc
    try:
        await app.state.vector._client.get_collections()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"qdrant: {exc}") from exc
    return {
        "status": "ready",
        "tenant": cfg.tenant,
        "embedding_model": cfg.ollama.embedding_model,
        "vector_size": cfg.qdrant.vector_size,
    }


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Count rejected /retrieve calls; keep FastAPI's usual 422 body.
    if request.url.path == "/retrieve":
        record_request(tool="retrieve_for_context", outcome="rejected")
    return JSONResponse(status_code=422, content={"detail": jsonable_errors(exc)})


def jsonable_errors(exc: RequestValidationError) -> list:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(exc.errors())


@app.post("/retrieve", response_model=RetrievalResponse)
async def retrieve(req: RetrievalRequest, request: Request) -> RetrievalResponse:
    try:
        return await _retrieve(req, request)
    except Exception:
        record_request(tool=req.tool, outcome="error")
        raise


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def _retrieve(req: RetrievalRequest, request: Request) -> RetrievalResponse:
    cfg: openCGConfig = app.state.cfg
    tracer: trace.Tracer = app.state.tracer
    catalog: CatalogStore = app.state.catalog
    audit: AuditStore = app.state.audit
    vector: VectorIndex = app.state.vector
    embeddings: OllamaEmbeddings = app.state.embeddings
    cid = req.correlation_id

    request_start = time.perf_counter()
    by_stage: list[StageUsage] = []

    # Continue the caller's trace (the MCP server sends W3C traceparent).
    parent = extract_context(request.headers)
    with stage_span(
        tracer,
        "pipeline.retrieve",
        cid,
        context=parent,
        tenant=req.identity.tenant,
        principal=req.identity.principal,
        tool=req.tool,
    ):
        # ----- Stage 1: identity ---------------------------------------------------
        t0 = time.perf_counter()
        with stage_span(tracer, "pipeline.identity", cid):
            ident = identity.run(req)
        observe_stage("identity", time.perf_counter() - t0)
        by_stage.append(StageUsage(stage="identity", latency_ms=_elapsed_ms(t0)))

        # ----- Stage 3: hybrid retrieval -------------------------------------------
        t0 = time.perf_counter()
        with stage_span(tracer, "pipeline.hybrid_retrieval", cid) as span:
            candidates, retr_tel = await hybrid_retrieval.run(
                tenant=ident.tenant,
                query=req.query,
                top_k=req.top_k or cfg.retrieval.default_top_k,
                catalog=catalog,
                vector=vector,
                embeddings=embeddings,
            )
            span.set_attribute("dense_count", retr_tel["dense_count"])
            span.set_attribute("lexical_count", retr_tel["lexical_count"])
            span.set_attribute("fused_count", retr_tel["fused_count"])
            span.set_attribute("tombstoned_filtered", retr_tel["tombstoned_filtered"])
            span.set_attribute("model", retr_tel["embed_model"])
            span.set_attribute("provider", retr_tel["embed_provider"])
            span.set_attribute("tokens_in", retr_tel["embed_tokens_in"])
        observe_stage("hybrid_retrieval", time.perf_counter() - t0)
        embed_cost = record_stage_tokens(
            stage="hybrid_retrieval",
            tenant=ident.tenant,
            tokens_in=retr_tel["embed_tokens_in"],
            tokens_out=0,
            model=retr_tel["embed_model"],
            provider=retr_tel["embed_provider"],
        )
        by_stage.append(
            StageUsage(
                stage="hybrid_retrieval",
                model=retr_tel["embed_model"],
                provider=retr_tel["embed_provider"],
                tokens_in=retr_tel["embed_tokens_in"],
                latency_ms=_elapsed_ms(t0),
                cost_usd=embed_cost,
            )
        )

        # ----- Stage 6 (collapsed): assemble + budget + permissive entitlement ----
        t0 = time.perf_counter()
        with stage_span(tracer, "pipeline.assemble", cid) as span:
            kept, decisions = assemble.run(
                candidates=candidates,
                roles=ident.roles,
                token_budget=req.token_budget or cfg.retrieval.default_token_budget,
                tokens_per_char=cfg.retrieval.tokens_per_char,
            )
            span.set_attribute("candidates_in", len(candidates))
            span.set_attribute("kept", len(kept))
            span.set_attribute("budget", req.token_budget or cfg.retrieval.default_token_budget)
        observe_stage("assemble", time.perf_counter() - t0)
        by_stage.append(StageUsage(stage="assemble", latency_ms=_elapsed_ms(t0)))

        # ----- Stage 7: build response + write audit -------------------------------
        fragments = [
            ContextFragment(
                entity_id=c.entity_id,
                source=c.source,
                source_uri=c.source_uri,
                title=c.title,
                text=c.text,
                score=c.score,
                tokens=estimate_tokens(c.text, tokens_per_char=cfg.retrieval.tokens_per_char),
                classification=c.classification,
            )
            for c in kept
        ]
        context_hash = hash_context([f.model_dump() for f in fragments])

        total_in = sum(s.tokens_in for s in by_stage)
        total_out = sum(s.tokens_out for s in by_stage)
        total_lat = int((time.perf_counter() - request_start) * 1000)
        by_provider, estimated_cost, cost_complete = summarise_by_provider(by_stage)

        audit_row = {
            "correlation_id": cid,
            "tenant": ident.tenant,
            "principal": ident.principal,
            "roles": list(ident.roles),
            "tool": req.tool,
            "query": req.query,
            "intent_plan": {"mvp": "hybrid_only"},
            "retriever_versions": {"pipeline": _VERSION},
            "model_versions": {"embeddings": retr_tel["embed_model"]},
            "vector_collection": None,
            "vector_snapshot_id": None,
            "candidate_ids": [c.entity_id for c in candidates],
            "candidate_decisions": decisions,
            "final_entity_ids": [c.entity_id for c in kept],
            "final_context_hash": context_hash,
            "tokens_in": total_in,
            "tokens_out": total_out,
            "latency_ms": total_lat,
            "outcome": "ok",
            "estimated_cost_usd": estimated_cost,
            "usage_by_provider": [p.model_dump() for p in by_provider],
        }
        await audit.write(audit_row)

        record_request(tool=req.tool, outcome="ok")

        return RetrievalResponse(
            correlation_id=cid,
            fragments=fragments,
            usage=UsageEnvelope(
                total_tokens_in=total_in,
                total_tokens_out=total_out,
                total_latency_ms=total_lat,
                by_stage=by_stage,
                by_provider=by_provider,
                estimated_cost_usd=estimated_cost,
                cost_complete=cost_complete,
            ),
            final_context_hash=context_hash,
        )


@app.get("/audit/recent")
async def audit_recent(limit: int = 50) -> dict:
    cfg: openCGConfig = app.state.cfg
    rows = await app.state.audit.list_recent(cfg.tenant, limit=limit)
    return {"items": rows}


@app.get("/audit/{audit_id}")
async def audit_detail(audit_id: int) -> dict:
    row = await app.state.audit.get(audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row
