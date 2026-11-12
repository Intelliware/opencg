"""FastAPI server for the ingestion service.

Exposes a small HTTP surface used by the admin UI (via the pipeline proxy):
  GET  /healthz      — liveness
  GET  /readyz       — readiness (storage backends reachable)
  GET  /connectors   — supported + deferred connectors
  POST /run/git      — start a git ingest in the background
  GET  /runs/recent  — in-memory history of recent runs

The `opencg-ingest` Click CLI still works via `docker compose exec`; both
share the same `pipeline_runner.run_sync` code path.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from opencg_pipeline.providers import OllamaEmbeddings
from opencg_pipeline.storage.catalog import CatalogStore
from opencg_shared import (
    ConnectorStatus,
    IngestionRun,
    load_config,
    metrics_app,
    openCGConfig,
    setup_otel,
)
from opencg_shared.otel import CORRELATION_HEADER, tag_request_span
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from starlette.routing import Route

from opencg_ingestion.pipeline_runner import run as ingest_run
from opencg_ingestion.repo_url import RepoUrlError, validate_repo_url
from opencg_ingestion.runs import RunStore

log = logging.getLogger(__name__)


_DEFERRED_REASONS = {
    "confluence": "deferred: ships with add-confluence-connector",
    "custom-api": "deferred: ships with add-custom-api-connector",
    "web": "deferred: ships with add-web-indexer",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    setup_otel(
        "opencg-ingestion",
        cfg.telemetry.service_namespace,
        config_endpoint=cfg.telemetry.otlp_endpoint,
    )
    runs = RunStore(cap=100)
    catalog = CatalogStore(cfg.postgres.url)
    await catalog.connect()
    app.state.cfg = cfg
    app.state.runs = runs
    app.state.catalog = catalog
    try:
        yield
    finally:
        await catalog.close()


app = FastAPI(title="opencg-ingestion", lifespan=lifespan)
app.router.routes.append(Route("/metrics", metrics_app))


@app.middleware("http")
async def _tag_correlation_id(request: Request, call_next):
    # FastAPI traces each request itself; tag its span so it (and, through
    # CorrelationIdSpanProcessor, its children) carry the caller's ID.
    tag_request_span(request.headers.get(CORRELATION_HEADER))
    return await call_next(request)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    cfg: openCGConfig = app.state.cfg
    # Postgres
    try:
        async with app.state.catalog._require_pool().acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres: {exc}") from exc
    # Qdrant
    qdrant = AsyncQdrantClient(url=cfg.qdrant.url)
    try:
        await qdrant.get_collections()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"qdrant: {exc}") from exc
    finally:
        await qdrant.close()
    # Ollama embeddings
    embeddings = OllamaEmbeddings(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embedding_model,
        api_key=cfg.ollama.api_key,
        provider=cfg.embeddings_endpoint().provider,
    )
    try:
        await embeddings.embed("readyz")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ollama: {exc}") from exc
    finally:
        await embeddings.close()
    return {"status": "ready"}


@app.get("/connectors", response_model=list[ConnectorStatus])
async def connectors() -> list[ConnectorStatus]:
    return [
        ConnectorStatus(name="git", supported=True),
        ConnectorStatus(name="confluence", supported=False, reason=_DEFERRED_REASONS["confluence"]),
        ConnectorStatus(name="custom-api", supported=False, reason=_DEFERRED_REASONS["custom-api"]),
        ConnectorStatus(name="web", supported=False, reason=_DEFERRED_REASONS["web"]),
    ]


class GitRunRequest(BaseModel):
    repo_url: str = Field(min_length=8)


@app.post("/run/git", response_model=IngestionRun)
async def run_git(req: GitRunRequest, bg: BackgroundTasks) -> IngestionRun:
    cfg: openCGConfig = app.state.cfg
    runs: RunStore = app.state.runs
    try:
        validate_repo_url(
            req.repo_url,
            allowed_hosts=cfg.ingestion.git.allowed_hosts,
            local_roots=cfg.ingestion.git.local_roots,
        )
    except RepoUrlError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "repo_url_rejected", "message": str(exc)}
        ) from exc
    run = await runs.add(connector="git", repo=req.repo_url)

    async def task() -> None:
        try:
            await runs.update(run.run_id, status="running")
            parents, chunks = await ingest_run(req.repo_url, cfg, run_id=run.run_id)
            await runs.update(
                run.run_id,
                status="succeeded",
                parents=parents,
                chunks=chunks,
                finished=True,
            )
        except Exception as exc:
            log.exception("git ingest failed for %s", req.repo_url)
            await runs.update(
                run.run_id,
                status="failed",
                error=str(exc),
                finished=True,
            )

    bg.add_task(task)
    return run


@app.get("/runs/recent", response_model=list[IngestionRun])
async def runs_recent() -> list[IngestionRun]:
    return await app.state.runs.list_recent()
