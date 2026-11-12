"""Tracing, metrics, cost and audit fields on /retrieve, plus model-call spans."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from opencg_pipeline import app as app_module
from opencg_pipeline.providers import EmbeddingResult, OllamaChat, OllamaEmbeddings
from opencg_shared import metrics, openCGConfig, pricing
from opencg_shared.config import PriceEntry
from opencg_shared.otel import CorrelationIdSpanProcessor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01"

# One global SDK provider for the whole module: OTel allows setting it once.
_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(CorrelationIdSpanProcessor())  # as setup_otel does
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_PROVIDER)


@pytest.fixture(autouse=True)
def _prices():
    pricing.configure(
        [
            PriceEntry(
                provider="ollama",
                model="nomic-embed-text",
                input_usd_per_1k=0.002,
                output_usd_per_1k=0,
                source="test",
                as_of=date(2026, 11, 12),
            )
        ]
    )
    _EXPORTER.clear()
    yield
    pricing.reset()


class _Embeddings:
    def __init__(self, provider: str = "ollama", model: str = "nomic-embed-text") -> None:
        self.provider = provider
        self.model = model

    async def embed(self, text: str) -> EmbeddingResult:
        cost = pricing.cost_usd(self.provider, self.model, 500, 0)
        return EmbeddingResult(
            vector=[0.1, 0.2],
            tokens_in=500,
            model=self.model,
            provider=self.provider,
            cost_usd=cost,
        )


class _Catalog:
    async def lexical_search(self, *, tenant: str, query: str, limit: int):
        return []

    async def live_entity_ids(self, *, tenant: str, entity_ids: list[str]) -> set[str]:
        return set(entity_ids)


class _Vector:
    async def search(self, *, sources: Any, vector: list[float], limit: int):
        return []


class _Audit:
    def __init__(self, fail: bool = False) -> None:
        self.rows: list[dict[str, Any]] = []
        self.fail = fail

    async def write(self, row: dict[str, Any]) -> int:
        if self.fail:
            raise RuntimeError("db down")
        self.rows.append(row)
        return len(self.rows)


def _client(*, embeddings=None, audit=None) -> tuple[TestClient, _Audit]:
    a = audit or _Audit()
    app = app_module.app
    app.state.cfg = openCGConfig()
    app.state.tracer = _PROVIDER.get_tracer("opencg-pipeline")
    app.state.catalog = _Catalog()
    app.state.vector = _Vector()
    app.state.embeddings = embeddings or _Embeddings()
    app.state.audit = a
    return TestClient(app, raise_server_exceptions=False), a


def _body(cid: str = "c-1") -> dict[str, Any]:
    return {
        "correlation_id": cid,
        "identity": {"principal": "p", "roles": ["reader"], "tenant": "default"},
        "tool": "retrieve_for_context",
        "query": "amber protocol",
    }


def _requests(outcome: str) -> float:
    return (
        metrics.REGISTRY.get_sample_value(
            "opencg_requests_total", {"tool": "retrieve_for_context", "outcome": outcome}
        )
        or 0.0
    )


def _stage_count(stage: str) -> float:
    return (
        metrics.REGISTRY.get_sample_value("opencg_stage_latency_seconds_count", {"stage": stage})
        or 0.0
    )


def test_retrieve_continues_incoming_trace_with_correlation_id_on_every_span():
    client, _ = _client()
    resp = client.post("/retrieve", json=_body("c-trace"), headers={"traceparent": TRACEPARENT})
    assert resp.status_code == 200
    spans = [s for s in _EXPORTER.get_finished_spans() if s.name.startswith("pipeline.")]
    assert {s.name for s in spans} >= {
        "pipeline.retrieve",
        "pipeline.identity",
        "pipeline.hybrid_retrieval",
        "pipeline.assemble",
    }
    assert all(format(s.context.trace_id, "032x") == TRACE_ID for s in spans)
    assert all(s.attributes.get("correlation_id") == "c-trace" for s in spans)


def test_retrieve_without_traceparent_starts_new_trace():
    client, _ = _client()
    assert client.post("/retrieve", json=_body()).status_code == 200
    spans = _EXPORTER.get_finished_spans()
    retrieve = next(s for s in spans if s.name == "pipeline.retrieve")
    in_trace = [s for s in spans if s.context.trace_id == retrieve.context.trace_id]
    roots = [s for s in in_trace if s.parent is None]
    assert len(roots) == 1
    assert format(retrieve.context.trace_id, "032x") != TRACE_ID


def test_framework_spans_inherit_correlation_id_from_header():
    client, _ = _client()
    resp = client.post(
        "/retrieve",
        json=_body("c-hdr"),
        headers={"traceparent": TRACEPARENT, "x-correlation-id": "c-hdr"},
    )
    assert resp.status_code == 200
    spans = [
        s for s in _EXPORTER.get_finished_spans() if format(s.context.trace_id, "032x") == TRACE_ID
    ]
    assert spans
    assert all(s.attributes.get("correlation_id") == "c-hdr" for s in spans), [
        (s.name, s.attributes.get("correlation_id")) for s in spans
    ]


def test_retrieve_usage_envelope_and_audit_carry_cost():
    client, audit = _client()
    usage = client.post("/retrieve", json=_body()).json()["usage"]
    assert usage["by_provider"] == [
        {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "tokens_in": 500,
            "tokens_out": 0,
            "cost_usd": pytest.approx(0.001),
        }
    ]
    assert usage["estimated_cost_usd"] == pytest.approx(0.001)
    assert usage["cost_complete"] is True
    assert sum(p["tokens_in"] for p in usage["by_provider"]) == usage["total_tokens_in"]
    row = audit.rows[-1]
    assert row["estimated_cost_usd"] == pytest.approx(0.001)
    assert row["usage_by_provider"][0]["provider"] == "ollama"


def test_retrieve_with_unpriced_provider_flags_incomplete_cost():
    client, _ = _client(embeddings=_Embeddings(provider="my-embedder", model="x"))
    usage = client.post("/retrieve", json=_body()).json()["usage"]
    assert usage["by_provider"][0]["provider"] == "my-embedder"
    assert usage["by_provider"][0]["cost_usd"] is None
    assert usage["cost_complete"] is False
    stage = next(s for s in usage["by_stage"] if s["stage"] == "hybrid_retrieval")
    assert stage["provider"] == "my-embedder"


def test_retrieve_times_every_stage_and_counts_ok():
    client, _ = _client()
    before = {s: _stage_count(s) for s in ("identity", "hybrid_retrieval", "assemble")}
    ok_before = _requests("ok")
    client.post("/retrieve", json=_body())
    assert all(_stage_count(s) == before[s] + 1 for s in before)
    assert _requests("ok") == ok_before + 1


def test_retrieve_error_and_rejected_outcomes():
    client, _ = _client(audit=_Audit(fail=True))
    err_before, rej_before = _requests("error"), _requests("rejected")
    assert client.post("/retrieve", json=_body()).status_code == 500
    assert _requests("error") == err_before + 1
    assert client.post("/retrieve", json={"query": "missing fields"}).status_code == 422
    assert _requests("rejected") == rej_before + 1


# --- model-call spans and provider errors ------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_embed_opens_model_span_with_cost_under_the_caller():
    respx.post("http://ollama:11434/api/embed").mock(
        return_value=Response(200, json={"embeddings": [[0.1]]})
    )
    client = OllamaEmbeddings(
        base_url="http://ollama:11434", model="nomic-embed-text", provider="ollama"
    )
    tracer = _PROVIDER.get_tracer("t")
    try:
        with tracer.start_as_current_span("pipeline.hybrid_retrieval") as parent:
            parent.set_attribute("correlation_id", "c-model")
            result = await client.embed("x" * 4000)
    finally:
        await client.close()
    assert result.cost_usd == pytest.approx(0.002)
    span = next(s for s in _EXPORTER.get_finished_spans() if s.name == "model.embed")
    assert span.parent.span_id == parent.get_span_context().span_id
    for key in ("provider", "model", "tokens_in", "tokens_out", "latency_ms", "cost_usd"):
        assert key in span.attributes
    assert span.attributes["correlation_id"] == "c-model"


@pytest.mark.asyncio
@respx.mock
async def test_chat_http_error_counts_provider_error():
    respx.post("https://ollama.com/api/chat").mock(return_value=Response(503))
    labels = {"provider": "ollama-cloud", "error_code": "503"}
    before = metrics.REGISTRY.get_sample_value("opencg_provider_errors_total", labels) or 0.0
    chat = OllamaChat(base_url="https://ollama.com", model="gemma3:4b", provider="ollama-cloud")
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await chat.chat(system=None, user="hi")
    finally:
        await chat.close()
    assert metrics.REGISTRY.get_sample_value("opencg_provider_errors_total", labels) == before + 1


@pytest.mark.asyncio
@respx.mock
async def test_chat_timeout_counts_provider_error():
    respx.post("https://ollama.com/api/chat").mock(side_effect=httpx.ReadTimeout("slow"))
    labels = {"provider": "ollama-cloud", "error_code": "timeout"}
    before = metrics.REGISTRY.get_sample_value("opencg_provider_errors_total", labels) or 0.0
    chat = OllamaChat(base_url="https://ollama.com", model="gemma3:4b", provider="ollama-cloud")
    try:
        with pytest.raises(httpx.ReadTimeout):
            await chat.chat(system=None, user="hi")
    finally:
        await chat.close()
    assert metrics.REGISTRY.get_sample_value("opencg_provider_errors_total", labels) == before + 1


def test_no_hard_coded_provider_labels():
    """Provider labels come from configuration, never a literal at the call site."""
    import pathlib
    import re

    roots = [
        pathlib.Path(app_module.__file__).parent,
        pathlib.Path(app_module.__file__).parents[3] / "ingestion" / "src",
    ]
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            if path.name == "providers.py":
                continue  # adapter defaults, overridden from config by every caller
            text = path.read_text()
            for match in re.finditer(r'provider\s*=\s*"(ollama|ollama-cloud)"', text):
                offenders.append(f"{path}:{match.group(0)}")
    assert offenders == []
