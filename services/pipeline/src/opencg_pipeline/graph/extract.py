"""LLM-based extractor for text chunks.

Called by the ingestion pipeline after a non-code chunk lands in the catalog
+ vector index. Asks a chat model (Ollama Cloud `gemma3:4b` by default) for
structured `{concepts, relations}` JSON, parses it, drops anything below
`min_confidence`, and returns a normalised `ExtractionResult` ready to hand
to the graph writer.

For code chunks the deterministic graphifyy extractor in
`services/ingestion/.../graph_writer.py` runs instead; this module never
sees them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass

from opencg_shared import ExtractionResult
from opencg_shared.metrics import (
    EXTRACTOR_EDGES,
    EXTRACTOR_ERRORS,
    STAGE_LATENCY,
    record_stage_tokens,
)
from opencg_shared.otel import current_correlation_id
from opentelemetry import trace

from opencg_pipeline.providers import OllamaChat

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_STAGE = "graph_extract_text"

# Output schema we ask the model to produce. Kept loose-but-typed; the
# `format=json` flag the chat client passes encourages valid JSON.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "relation": {"type": "string"},
                    "to": {"type": "string"},
                    "evidence_span": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["from", "relation", "to", "confidence"],
            },
        },
    },
}


@dataclass
class ExtractionTelemetry:
    """Counters the caller emits as OTel attributes / Prom counters."""

    tokens_in: int
    tokens_out: int
    raw_concepts: int
    raw_relations: int
    kept_concepts: int
    kept_relations: int
    dropped_unknown_vocab: int
    dropped_low_confidence: int
    parse_failed: bool


def build_prompt(text: str, vocabulary: list[str]) -> tuple[str, str]:
    """Construct the (system, user) prompt pair.

    The system prompt names the in-vocabulary relation set so the model picks
    valid types most of the time; out-of-vocab relations still get dropped
    downstream as a defence-in-depth.
    """
    vocab_str = ", ".join(sorted(vocabulary))
    system = (
        "You are a careful information extractor. From the user's text, "
        "produce ONLY a JSON object with two arrays:\n"
        '  "concepts": [{"name", "description"?, "aliases"?[]}],\n'
        '  "relations": [{"from","relation","to","evidence_span"?,"confidence"}].\n'
        "Each relation `confidence` is a number in [0,1].\n"
        f"Use relation names from this vocabulary only: {vocab_str}.\n"
        "Concept names are short noun phrases (1-4 words). Be conservative — "
        "only emit relations the text clearly supports. Output JSON only, "
        "no commentary."
    )
    user = text.strip()
    if len(user) > 8000:
        user = user[:8000] + "\n…[truncated]"
    return system, user


def _normalize(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def parse_response(raw: str) -> ExtractionResult | None:
    """Parse a chat-model response into an `ExtractionResult`.

    Returns `None` on any parse failure — the caller should log + increment
    the parse-failure counter without raising so a single bad chunk does
    not abort the ingest. Tolerates a model that wraps the JSON in
    ``` code fences ``` or prefixes/suffixes natural language.
    """
    s = raw.strip()
    # Strip code fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    # Find the first {...} object span.
    first_brace = s.find("{")
    last_brace = s.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return None
    candidate = s[first_brace : last_brace + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    try:
        return ExtractionResult.model_validate(data)
    except Exception:
        return None


def filter_result(
    result: ExtractionResult,
    *,
    vocabulary: list[str],
    min_confidence: float,
) -> tuple[ExtractionResult, int, int]:
    """Drop out-of-vocab and low-confidence relations.

    Returns (filtered_result, dropped_unknown_vocab, dropped_low_confidence).
    Concepts that no surviving relation references are still kept — they may
    be standalone nouns worth recording.
    """
    vocab_set = set(vocabulary)
    kept_relations = []
    dropped_unknown = 0
    dropped_low = 0
    for rel in result.relations:
        if rel.relation not in vocab_set:
            dropped_unknown += 1
            continue
        if rel.confidence < min_confidence:
            dropped_low += 1
            continue
        if not _normalize(rel.from_) or not _normalize(rel.to):
            continue
        kept_relations.append(rel)
    # Concepts: keep all, but normalise names — the writer will dedupe.
    kept_concepts = [c for c in result.concepts if _normalize(c.name)]
    return (
        ExtractionResult(concepts=kept_concepts, relations=kept_relations),
        dropped_unknown,
        dropped_low,
    )


async def extract_for_chunk(
    *,
    chunk_text: str,
    chunk_entity_id: str | None = None,
    vocabulary: list[str],
    chat: OllamaChat,
    tenant: str = "default",
    min_confidence: float = 0.6,
    timeout_seconds: float = 30.0,
) -> tuple[ExtractionResult, ExtractionTelemetry]:
    """Run the LLM extractor against one chunk.

    Returns (result, telemetry). The result may have empty `concepts` and
    `relations` lists — that's the model saying "nothing here" and is a
    normal outcome. Raises only on transport/timeout/HTTP errors so the
    caller can decide whether to log-and-continue (the typical case) or
    propagate.
    """
    system, user = build_prompt(chunk_text, vocabulary)
    started = time.perf_counter()
    with tracer.start_as_current_span("pipeline.graph_extract_text") as span:
        correlation_id = current_correlation_id()
        if correlation_id:
            span.set_attribute("correlation_id", correlation_id)
        span.set_attribute("stage", _STAGE)
        span.set_attribute("tenant", tenant)
        if chunk_entity_id:
            span.set_attribute("chunk_entity_id", chunk_entity_id)
        try:
            chat_result = await asyncio.wait_for(
                chat.chat(system=system, user=user, response_schema=_RESPONSE_SCHEMA),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            EXTRACTOR_ERRORS.labels(reason="timeout").inc()
            span.set_attribute("error.reason", "timeout")
            log.warning(
                "extract: chat timeout after %.1fs for chunk %s",
                timeout_seconds,
                chunk_entity_id or "unknown",
            )
            raise
        except Exception:
            EXTRACTOR_ERRORS.labels(reason="provider").inc()
            span.set_attribute("error.reason", "provider")
            raise

        latency_seconds = time.perf_counter() - started
        latency_ms = latency_seconds * 1000
        STAGE_LATENCY.labels(stage=_STAGE).observe(latency_seconds)
        cost = record_stage_tokens(
            stage=_STAGE,
            tenant=tenant,
            model=chat_result.model,
            provider=chat_result.provider,
            tokens_in=chat_result.tokens_in,
            tokens_out=chat_result.tokens_out,
        )
        span.set_attribute("model", chat_result.model)
        span.set_attribute("provider", chat_result.provider)
        span.set_attribute("tokens_in", chat_result.tokens_in)
        span.set_attribute("tokens_out", chat_result.tokens_out)
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("cost_usd", cost if cost is not None else -1.0)
        span.set_attribute("cost_priced", cost is not None)

        parsed = parse_response(chat_result.content)
        if parsed is None:
            EXTRACTOR_ERRORS.labels(reason="parse").inc()
            span.set_attribute("error.reason", "parse")
            log.warning(
                "extract: failed to parse chat response for chunk %s (%d chars)",
                chunk_entity_id or "unknown",
                len(chat_result.content),
            )
            raise ValueError("graph extractor returned invalid JSON")

        raw_concepts = len(parsed.concepts)
        raw_relations = len(parsed.relations)
        filtered, dropped_unknown, dropped_low = filter_result(
            parsed, vocabulary=vocabulary, min_confidence=min_confidence
        )
        for relation in filtered.relations:
            EXTRACTOR_EDGES.labels(
                relation=relation.relation,
                state="candidate",
            ).inc()
        telemetry = ExtractionTelemetry(
            tokens_in=chat_result.tokens_in,
            tokens_out=chat_result.tokens_out,
            raw_concepts=raw_concepts,
            raw_relations=raw_relations,
            kept_concepts=len(filtered.concepts),
            kept_relations=len(filtered.relations),
            dropped_unknown_vocab=dropped_unknown,
            dropped_low_confidence=dropped_low,
            parse_failed=False,
        )
        return filtered, telemetry
