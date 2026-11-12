"""FastAPI app — the retrieval pipeline."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
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
from opencg_shared.auth import Authenticator, settings_from_env, startup_checks
from opencg_shared.authz import OpaClient, PolicyUnavailable
from opencg_shared.metrics import observe_stage
from opencg_shared.otel import CORRELATION_HEADER, tag_request_span
from opentelemetry import trace
from starlette.routing import Route

from opencg_pipeline import admin_routes, security
from opencg_pipeline.graph import routes as graph_routes
from opencg_pipeline.providers import OllamaEmbeddings
from opencg_pipeline.stages import assemble, entitle, hybrid_retrieval, identity
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
    # Refuse unsafe auth configuration before serving anything (design D1, D1a).
    auth_settings = settings_from_env(
        tenant=cfg.tenant, stub_principal=cfg.identity.principal, stub_roles=cfg.identity.roles
    )
    startup_checks(auth_settings)
    authenticator = Authenticator(auth_settings)
    opa = OpaClient()
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
    app.state.authenticator = authenticator
    app.state.opa = opa
    app.state.audit_pool = audit._pool_required()
    try:
        yield
    finally:
        await catalog.close()
        await audit.close()
        await graph.close()
        await vector.close()
        await embeddings.close()
        await ingestion_client.aclose()
        await authenticator.close()
        await opa.close()


app = FastAPI(title="opencg-pipeline", lifespan=lifespan, dependencies=[Depends(security.guard)])
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
            has_access_log = await conn.fetchval(
                "SELECT to_regclass('opencg.access_audit_log') IS NOT NULL"
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres: {exc}") from exc
    if not has_access_log:
        raise HTTPException(
            status_code=503,
            detail="postgres: opencg.access_audit_log is missing; apply "
            "infra/postgres/init/070_access_audit.sql (make db-apply SQL=...)",
        )
    if not await app.state.opa.ready():
        raise HTTPException(status_code=503, detail="opa: not reachable")
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
    auth = security.auth_of(request)
    # oidc / api-key: identity from the token only; none: the body's, else the stub.
    ident_in = security.body_identity_or(request, req.identity)
    req = req.model_copy(update={"identity": ident_in})

    request_start = time.perf_counter()
    by_stage: list[StageUsage] = []

    if getattr(request.state, "policy_unavailable", False):
        await _write_error_audit(audit, req, auth.auth_method, "policy_unavailable", request_start)
        raise _policy_unavailable()

    # Continue the caller's trace (the MCP server sends W3C traceparent).
    parent = extract_context(request.headers)
    with stage_span(
        tracer,
        "pipeline.retrieve",
        cid,
        context=parent,
        tenant=req.identity.tenant,
        principal=req.identity.principal,
        auth_method=auth.auth_method,
        tool=req.tool,
    ):
        # ----- Stage 1: identity ---------------------------------------------------
        t0 = time.perf_counter()
        with stage_span(
            tracer,
            "pipeline.identity",
            cid,
            principal=req.identity.principal,
            tenant=req.identity.tenant,
            auth_method=auth.auth_method,
        ):
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

        # ----- Stage 5: entitle (one OPA call; denied never use budget) -----------
        t0 = time.perf_counter()
        with stage_span(tracer, "pipeline.entitle", cid) as span:
            try:
                ent = await entitle.run(
                    opa=app.state.opa,
                    identity=ident,
                    auth_method=auth.auth_method,
                    tool=req.tool,
                    correlation_id=cid,
                    candidates=candidates,
                )
            except PolicyUnavailable as exc:
                log.warning("entitlement unavailable: %s", exc)
                span.set_attribute("error.reason", "policy_unavailable")
                await _write_error_audit(
                    audit, req, auth.auth_method, "policy_unavailable", request_start, candidates
                )
                raise _policy_unavailable() from None
            span.set_attribute("candidates_in", len(candidates))
            span.set_attribute("denied", len(ent.denied))
            span.set_attribute("policy_revision", ent.result.revision)
            span.set_attribute("latency_ms", _elapsed_ms(t0))
        observe_stage("entitle", time.perf_counter() - t0)
        by_stage.append(StageUsage(stage="entitle", latency_ms=_elapsed_ms(t0)))

        # ----- Stage 6: assemble (token budget) -----------------------------------
        t0 = time.perf_counter()
        with stage_span(tracer, "pipeline.assemble", cid) as span:
            kept, budget_decisions = assemble.run(
                candidates=ent.allowed,
                token_budget=req.token_budget or cfg.retrieval.default_token_budget,
                tokens_per_char=cfg.retrieval.tokens_per_char,
            )
            span.set_attribute("candidates_in", len(ent.allowed))
            span.set_attribute("kept", len(kept))
            span.set_attribute("budget", req.token_budget or cfg.retrieval.default_token_budget)
        observe_stage("assemble", time.perf_counter() - t0)
        by_stage.append(StageUsage(stage="assemble", latency_ms=_elapsed_ms(t0)))
        # Every candidate, in retrieval order: deny (policy), drop (budget) or include.
        by_id = {d["entity_id"]: d for d in [*ent.denied, *budget_decisions]}
        decisions = [by_id[c.entity_id] for c in candidates if c.entity_id in by_id]

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
            "auth_method": auth.auth_method,
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


def _policy_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "policy_unavailable",
            "message": "the access policy could not be evaluated",
        },
    )


async def _write_error_audit(
    audit: AuditStore,
    req: RetrievalRequest,
    auth_method: str,
    error_code: str,
    started: float,
    candidates: list | None = None,
) -> None:
    """Fail-closed retrieval still leaves an audit row (outcome = error, no fragments)."""
    await audit.write(
        {
            "correlation_id": req.correlation_id,
            "tenant": req.identity.tenant,
            "principal": req.identity.principal,
            "roles": list(req.identity.roles),
            "tool": req.tool,
            "query": req.query,
            "intent_plan": {"mvp": "hybrid_only"},
            "retriever_versions": {"pipeline": _VERSION},
            "candidate_ids": [c.entity_id for c in candidates or []],
            "candidate_decisions": [],
            "final_entity_ids": [],
            "final_context_hash": hash_context([]),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "outcome": "error",
            "error_code": error_code,
            "auth_method": auth_method,
        }
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
