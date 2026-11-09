"""Prometheus counters/histograms shared across services.

The standard metric set spec'd in observability/spec.md:
  opencg_requests_total{tool,outcome}
  opencg_stage_latency_seconds_bucket{stage}
  opencg_tokens_total{stage,model,provider,tenant,direction}
  opencg_provider_errors_total{provider,error_code}
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response

REGISTRY = CollectorRegistry()

REQUESTS = Counter(
    "opencg_requests_total",
    "MCP/pipeline requests by tool and outcome.",
    labelnames=("tool", "outcome"),
    registry=REGISTRY,
)
STAGE_LATENCY = Histogram(
    "opencg_stage_latency_seconds",
    "Per-stage latency in seconds.",
    labelnames=("stage",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=REGISTRY,
)
TOKENS = Counter(
    "opencg_tokens_total",
    "Token counts per stage/model/provider/tenant/direction.",
    labelnames=("stage", "model", "provider", "tenant", "direction"),
    registry=REGISTRY,
)
PROVIDER_ERRORS = Counter(
    "opencg_provider_errors_total",
    "Errors emitted by model providers.",
    labelnames=("provider", "error_code"),
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


def record_stage_tokens(
    *,
    stage: str,
    tenant: str,
    tokens_in: int,
    tokens_out: int,
    model: str | None = None,
    provider: str | None = None,
) -> None:
    if tokens_in:
        TOKENS.labels(
            stage=stage,
            model=model or "n/a",
            provider=provider or "n/a",
            tenant=tenant,
            direction="in",
        ).inc(tokens_in)
    if tokens_out:
        TOKENS.labels(
            stage=stage,
            model=model or "n/a",
            provider=provider or "n/a",
            tenant=tenant,
            direction="out",
        ).inc(tokens_out)


async def metrics_app(request: Request) -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
