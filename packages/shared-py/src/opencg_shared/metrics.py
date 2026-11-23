"""Prometheus counters/histograms shared across services.

The standard metric set (see the `observability` capability):
  opencg_requests_total{tool,outcome}
  opencg_stage_latency_seconds{stage}                      histogram
  opencg_tokens_total{stage,model,provider,tenant,direction}
  opencg_cost_usd_total{provider,model,tenant}
  opencg_cost_unpriced_tokens_total{provider,model}
  opencg_provider_errors_total{provider,error_code}
  opencg_audit_writes_total{log,outcome}
  opencg_ingestion_runs_total{connector,status}
  opencg_ingestion_documents_total{connector}
  opencg_ingestion_chunks_total{connector}
  opencg_ingestion_run_duration_seconds{connector}         histogram
  opencg_extractor_edges_total{relation,state}
  opencg_extractor_errors_total{reason}
  opencg_auth_failures_total{service,reason}

Multiprocess mode: when `PROMETHEUS_MULTIPROC_DIR` is set (the ingestion
container sets it so one-shot CLI runs are counted), every process writes its
values to memory-mapped files in that directory and `metrics_app` serves the
sum across processes. Only counters and histograms are used, so no gauge
`multiprocess_mode` is needed; a future gauge must declare one.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.requests import Request
from starlette.responses import Response

from opencg_shared import pricing

MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"

REGISTRY = CollectorRegistry()

REQUESTS = Counter(
    "opencg_requests_total",
    "MCP/pipeline requests by tool and outcome (ok, error, rejected).",
    labelnames=("tool", "outcome"),
    registry=REGISTRY,
)
STAGE_LATENCY = Histogram(
    "opencg_stage_latency_seconds",
    "Per-stage latency in seconds.",
    labelnames=("stage",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRY,
)
TOKENS = Counter(
    "opencg_tokens_total",
    "Token counts per stage/model/provider/tenant/direction.",
    labelnames=("stage", "model", "provider", "tenant", "direction"),
    registry=REGISTRY,
)
COST_USD = Counter(
    "opencg_cost_usd_total",
    "Estimated model cost in USD, from the configured price table.",
    labelnames=("provider", "model", "tenant"),
    registry=REGISTRY,
)
COST_UNPRICED_TOKENS = Counter(
    "opencg_cost_unpriced_tokens_total",
    "Tokens used by (provider, model) pairs with no price entry.",
    labelnames=("provider", "model"),
    registry=REGISTRY,
)
PROVIDER_ERRORS = Counter(
    "opencg_provider_errors_total",
    "Errors emitted by model providers (HTTP status or 'timeout').",
    labelnames=("provider", "error_code"),
    registry=REGISTRY,
)
AUDIT_WRITES = Counter(
    "opencg_audit_writes_total",
    "Audit log writes by log and outcome.",
    labelnames=("log", "outcome"),
    registry=REGISTRY,
)
INGESTION_RUNS = Counter(
    "opencg_ingestion_runs_total",
    "Ingestion runs by connector and final status.",
    labelnames=("connector", "status"),
    registry=REGISTRY,
)
INGESTION_DOCUMENTS = Counter(
    "opencg_ingestion_documents_total",
    "Documents processed by ingestion runs.",
    labelnames=("connector",),
    registry=REGISTRY,
)
INGESTION_CHUNKS = Counter(
    "opencg_ingestion_chunks_total",
    "Chunks written by ingestion runs.",
    labelnames=("connector",),
    registry=REGISTRY,
)
INGESTION_RUN_DURATION = Histogram(
    "opencg_ingestion_run_duration_seconds",
    "Ingestion run wall-clock duration in seconds.",
    labelnames=("connector",),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
    registry=REGISTRY,
)
AUTH_FAILURES = Counter(
    "opencg_auth_failures_total",
    "Failed authentications by service and reason.",
    labelnames=("service", "reason"),
    registry=REGISTRY,
)
EXTRACTOR_EDGES = Counter(
    "opencg_extractor_edges_total",
    "Relationship edges emitted by extractors.",
    labelnames=("relation", "state"),
    registry=REGISTRY,
)
EXTRACTOR_ERRORS = Counter(
    "opencg_extractor_errors_total",
    "Graph extractor failures by reason.",
    labelnames=("reason",),
    registry=REGISTRY,
)


def record_request(tool: str, outcome: str) -> None:
    REQUESTS.labels(tool=tool, outcome=outcome).inc()


def observe_stage(stage: str, seconds: float) -> None:
    STAGE_LATENCY.labels(stage=stage).observe(seconds)


@contextmanager
def timed_stage(stage: str) -> Iterator[None]:
    """Observe `opencg_stage_latency_seconds{stage}` around a block."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        observe_stage(stage, time.perf_counter() - t0)


def record_provider_error(provider: str | None, error_code: str | int) -> None:
    PROVIDER_ERRORS.labels(provider=provider or "n/a", error_code=str(error_code)).inc()


def record_auth_failure(service: str, reason: str) -> None:
    AUTH_FAILURES.labels(service=service, reason=reason).inc()


def record_audit_write(log: str, outcome: str) -> None:
    AUDIT_WRITES.labels(log=log, outcome=outcome).inc()


def record_ingestion_run(
    *,
    connector: str,
    status: str,
    documents: int = 0,
    chunks: int = 0,
    duration_seconds: float | None = None,
) -> None:
    INGESTION_RUNS.labels(connector=connector, status=status).inc()
    if documents:
        INGESTION_DOCUMENTS.labels(connector=connector).inc(documents)
    if chunks:
        INGESTION_CHUNKS.labels(connector=connector).inc(chunks)
    if duration_seconds is not None:
        INGESTION_RUN_DURATION.labels(connector=connector).observe(duration_seconds)


def record_stage_tokens(
    *,
    stage: str,
    tenant: str,
    tokens_in: int,
    tokens_out: int,
    model: str | None = None,
    provider: str | None = None,
) -> float | None:
    """Count tokens and their estimated cost.

    Returns the cost in USD, or `None` when the (provider, model) pair has no
    price entry; in that case the tokens go to the unpriced counter instead.
    """
    model_l = model or "n/a"
    provider_l = provider or "n/a"
    if tokens_in:
        TOKENS.labels(
            stage=stage, model=model_l, provider=provider_l, tenant=tenant, direction="in"
        ).inc(tokens_in)
    if tokens_out:
        TOKENS.labels(
            stage=stage, model=model_l, provider=provider_l, tenant=tenant, direction="out"
        ).inc(tokens_out)
    cost = pricing.cost_usd(provider, model, tokens_in, tokens_out)
    if cost is None:
        if tokens_in or tokens_out:
            COST_UNPRICED_TOKENS.labels(provider=provider_l, model=model_l).inc(
                tokens_in + tokens_out
            )
    else:
        COST_USD.labels(provider=provider_l, model=model_l, tenant=tenant).inc(cost)
    return cost


def _registry_for_scrape() -> CollectorRegistry:
    if os.environ.get(MULTIPROC_ENV):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY


def render_latest() -> bytes:
    return generate_latest(_registry_for_scrape())


async def metrics_app(request: Request) -> Response:
    return Response(render_latest(), media_type=CONTENT_TYPE_LATEST)
