"""Pricing, provider labels, metrics, usage summaries and span helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from opencg_shared import metrics, pricing
from opencg_shared.config import PriceEntry, load_config
from opencg_shared.otel import extract_context, resolve_endpoint, stage_span
from opencg_shared.types import StageUsage, summarise_by_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]


def _entry(provider: str, model: str, i: float, o: float) -> PriceEntry:
    return PriceEntry(
        provider=provider,
        model=model,
        input_usd_per_1k=i,
        output_usd_per_1k=o,
        source="test",
        as_of=date(2026, 11, 12),
    )


@pytest.fixture(autouse=True)
def _price_table():
    pricing.configure(
        [
            _entry("ollama", "nomic-embed-text", 0, 0),
            _entry("anthropic", "claude-haiku", 0.001, 0.005),
        ]
    )
    yield
    pricing.reset()


def _sample(name: str, labels: dict[str, str]) -> float:
    value = metrics.REGISTRY.get_sample_value(name, labels)
    return value or 0.0


# --- pricing ----------------------------------------------------------------


def test_priced_call_cost():
    assert pricing.cost_usd("anthropic", "claude-haiku", 500, 100) == pytest.approx(0.001)


def test_zero_priced_is_zero_not_unpriced():
    assert pricing.cost_usd("ollama", "nomic-embed-text", 1000, 0) == 0.0


def test_unpriced_is_none_and_warns_once(caplog):
    with caplog.at_level("WARNING"):
        assert pricing.cost_usd("ollama-cloud", "gemma3:4b", 10, 10) is None
        assert pricing.cost_usd("ollama-cloud", "gemma3:4b", 10, 10) is None
    warnings = [r for r in caplog.records if "gemma3:4b" in r.getMessage()]
    assert len(warnings) == 1


def test_cost_rounds_to_six_places():
    pricing.configure([_entry("p", "m", 0.0000001, 0)])
    assert pricing.cost_usd("p", "m", 1, 0) == 0.0


@pytest.mark.parametrize("missing", ["source", "as_of"])
def test_price_entry_requires_provenance(missing):
    data = {
        "provider": "p",
        "model": "m",
        "input_usd_per_1k": 0,
        "output_usd_per_1k": 0,
        "source": "x",
        "as_of": "2026-11-12",
    }
    del data[missing]
    with pytest.raises(ValidationError):
        PriceEntry.model_validate(data)


def test_checked_in_price_table_loads():
    cfg = load_config(REPO_ROOT / "opencg.yaml")
    keys = {(e.provider, e.model) for e in cfg.observability.pricing}
    assert ("ollama", "nomic-embed-text") in keys
    assert all(e.source and e.as_of for e in cfg.observability.pricing)
    assert any(p == "ollama-cloud" for p, _ in keys)


# --- provider labels ----------------------------------------------------------


def test_default_config_labels_cloud_chat_apart(monkeypatch):
    monkeypatch.delenv("OPENCG__PROVIDERS__CHAT__PROVIDER", raising=False)
    cfg = load_config(REPO_ROOT / "opencg.yaml")
    assert cfg.providers.chat.provider == "ollama-cloud"
    assert cfg.embeddings_endpoint().provider == "ollama"


def test_legacy_ollama_label_on_cloud_url_resolves(tmp_path):
    f = tmp_path / "opencg.yaml"
    f.write_text(
        "providers:\n  chat:\n    provider: ollama\n    base_url: https://ollama.com\n"
        "    model: gemma3:4b\n"
    )
    assert load_config(f).providers.chat.provider == "ollama-cloud"


def test_local_ollama_label_unchanged(tmp_path):
    f = tmp_path / "opencg.yaml"
    f.write_text(
        "providers:\n  chat:\n    provider: ollama\n    base_url: http://ollama:11434\n"
        "    model: gemma3:4b\n"
    )
    assert load_config(f).providers.chat.provider == "ollama"


def test_custom_embeddings_label(tmp_path):
    f = tmp_path / "opencg.yaml"
    f.write_text(
        "ollama:\n  base_url: http://ollama:11434\n  embedding_model: e\n"
        "providers:\n  embeddings:\n    provider: my-embedder\n"
        "    base_url: http://ollama:11434\n    model: e\n"
    )
    assert load_config(f).embeddings_endpoint().provider == "my-embedder"


# --- metrics ------------------------------------------------------------------


def test_record_stage_tokens_pairs_cost():
    labels = {"provider": "anthropic", "model": "claude-haiku", "tenant": "t-cost"}
    before = _sample("opencg_cost_usd_total", labels)
    cost = metrics.record_stage_tokens(
        stage="s",
        tenant="t-cost",
        tokens_in=500,
        tokens_out=100,
        model="claude-haiku",
        provider="anthropic",
    )
    assert cost == pytest.approx(0.001)
    assert _sample("opencg_cost_usd_total", labels) - before == pytest.approx(0.001)


def test_unpriced_tokens_counted_separately():
    unpriced = {"provider": "ollama-cloud", "model": "unpriced-model"}
    before = _sample("opencg_cost_unpriced_tokens_total", unpriced)
    cost = metrics.record_stage_tokens(
        stage="s",
        tenant="t-unpriced",
        tokens_in=7,
        tokens_out=3,
        model="unpriced-model",
        provider="ollama-cloud",
    )
    assert cost is None
    assert _sample("opencg_cost_unpriced_tokens_total", unpriced) - before == 10
    assert (
        _sample(
            "opencg_cost_usd_total",
            {"provider": "ollama-cloud", "model": "unpriced-model", "tenant": "t-unpriced"},
        )
        == 0
    )


def test_ingestion_run_and_audit_helpers():
    metrics.record_ingestion_run(
        connector="git-test", status="succeeded", documents=2, chunks=5, duration_seconds=1.5
    )
    metrics.record_audit_write("retrieval-test", "ok")
    metrics.record_provider_error("ollama-test", 503)
    assert _sample("opencg_ingestion_runs_total", {"connector": "git-test", "status": "succeeded"})
    assert _sample("opencg_ingestion_chunks_total", {"connector": "git-test"}) >= 5
    assert _sample("opencg_audit_writes_total", {"log": "retrieval-test", "outcome": "ok"})
    assert _sample("opencg_provider_errors_total", {"provider": "ollama-test", "error_code": "503"})


def test_multiprocess_counters_survive_the_writing_process(tmp_path, monkeypatch):
    """A counter bumped by a short-lived process shows up in the server's scrape."""
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    code = (
        "from opencg_shared.metrics import record_ingestion_run;"
        "record_ingestion_run(connector='git', status='succeeded', documents=1, chunks=3)"
    )
    subprocess.run([sys.executable, "-c", code], env=env, check=True)
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    body = metrics.render_latest().decode()
    assert 'opencg_ingestion_runs_total{connector="git",status="succeeded"} 1.0' in body
    assert 'opencg_ingestion_chunks_total{connector="git"} 3.0' in body


# --- usage summary ------------------------------------------------------------


def test_summarise_by_provider_sums_and_flags_unpriced():
    stages = [
        StageUsage(stage="identity"),
        StageUsage(stage="a", provider="ollama", model="e", tokens_in=5, cost_usd=0.0),
        StageUsage(stage="b", provider="ollama", model="e", tokens_in=3, cost_usd=0.0),
        StageUsage(
            stage="c", provider="cloud", model="c", tokens_in=2, tokens_out=4, cost_usd=0.01
        ),
        StageUsage(stage="d", provider="cloud", model="x", tokens_in=1, cost_usd=None),
    ]
    by_provider, total, complete = summarise_by_provider(stages)
    assert [(p.provider, p.model, p.tokens_in) for p in by_provider] == [
        ("ollama", "e", 8),
        ("cloud", "c", 2),
        ("cloud", "x", 1),
    ]
    assert by_provider[2].cost_usd is None
    assert total == pytest.approx(0.01)
    assert complete is False
    assert sum(p.tokens_in for p in by_provider) == 11


def test_summarise_all_priced_is_complete():
    _, total, complete = summarise_by_provider(
        [StageUsage(stage="a", provider="p", model="m", tokens_in=1, cost_usd=0.002)]
    )
    assert complete is True
    assert total == pytest.approx(0.002)


# --- tracing helpers ------------------------------------------------------------


def test_stage_span_continues_incoming_trace_and_sets_correlation_id():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    ctx = extract_context({"traceparent": f"00-{trace_id}-00f067aa0ba902b7-01"})
    with stage_span(tracer, "pipeline.retrieve", "c-1", context=ctx):
        with stage_span(tracer, "pipeline.identity", "c-1"):
            pass
    spans = exporter.get_finished_spans()
    assert {s.name for s in spans} == {"pipeline.retrieve", "pipeline.identity"}
    assert all(format(s.context.trace_id, "032x") == trace_id for s in spans)
    assert all(s.attributes["correlation_id"] == "c-1" for s in spans)


def test_endpoint_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert resolve_endpoint("http://collector:4318") == "http://collector:4318"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "none")
    assert resolve_endpoint("http://collector:4318") == "none"
