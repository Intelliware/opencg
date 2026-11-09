from __future__ import annotations

import asyncio
import json

import pytest
from opencg_pipeline.graph.extract import (
    build_prompt,
    extract_for_chunk,
    filter_result,
    parse_response,
)
from opencg_pipeline.providers import ChatResult
from opencg_shared import ExtractionResult

VOCAB = ["depends_on", "defined_in", "mentions", "related_to", "causes"]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def test_prompt_includes_vocabulary_names():
    system, user = build_prompt("the auth middleware logs every request", VOCAB)
    for name in VOCAB:
        assert name in system
    assert "the auth middleware" in user


def test_prompt_truncates_oversize_user_text():
    long = "x" * 20_000
    _, user = build_prompt(long, VOCAB)
    assert len(user) <= 8100
    assert user.endswith("[truncated]")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_response_simple_object():
    raw = json.dumps(
        {
            "concepts": [{"name": "Authentication"}],
            "relations": [
                {
                    "from": "Authentication",
                    "relation": "depends_on",
                    "to": "Token Store",
                    "confidence": 0.9,
                }
            ],
        }
    )
    r = parse_response(raw)
    assert r is not None
    assert r.concepts[0].name == "Authentication"
    assert r.relations[0].from_ == "Authentication"


def test_parse_response_handles_code_fences():
    raw = "```json\n" + json.dumps({"concepts": [{"name": "X"}], "relations": []}) + "\n```"
    r = parse_response(raw)
    assert r is not None and r.concepts[0].name == "X"


def test_parse_response_handles_leading_chatter():
    raw = "Sure, here you go:\n" + json.dumps({"concepts": [], "relations": []})
    r = parse_response(raw)
    assert r is not None


def test_parse_response_returns_none_on_garbage():
    assert parse_response("Sorry I cannot help with that") is None
    assert parse_response("") is None
    assert parse_response("{ this is not json") is None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_filter_drops_unknown_relation():
    r = ExtractionResult.model_validate(
        {
            "concepts": [],
            "relations": [
                {"from": "A", "relation": "calls", "to": "B", "confidence": 0.9},  # not in vocab
                {"from": "A", "relation": "depends_on", "to": "B", "confidence": 0.9},
            ],
        }
    )
    out, unknown, low = filter_result(r, vocabulary=VOCAB, min_confidence=0.6)
    assert unknown == 1
    assert low == 0
    assert len(out.relations) == 1
    assert out.relations[0].relation == "depends_on"


def test_filter_drops_low_confidence():
    r = ExtractionResult.model_validate(
        {
            "concepts": [],
            "relations": [
                {"from": "A", "relation": "depends_on", "to": "B", "confidence": 0.5},
                {"from": "A", "relation": "depends_on", "to": "C", "confidence": 0.7},
            ],
        }
    )
    out, unknown, low = filter_result(r, vocabulary=VOCAB, min_confidence=0.6)
    assert unknown == 0
    assert low == 1
    assert len(out.relations) == 1
    assert out.relations[0].to == "C"


def test_filter_drops_empty_endpoints():
    r = ExtractionResult.model_validate(
        {
            "concepts": [],
            "relations": [
                {"from": "  ", "relation": "depends_on", "to": "B", "confidence": 0.9},
                {"from": "A", "relation": "depends_on", "to": "", "confidence": 0.9},
                {"from": "A", "relation": "depends_on", "to": "C", "confidence": 0.9},
            ],
        }
    )
    out, _, _ = filter_result(r, vocabulary=VOCAB, min_confidence=0.6)
    assert len(out.relations) == 1


# ---------------------------------------------------------------------------
# extract_for_chunk
# ---------------------------------------------------------------------------


class _FakeChat:
    """Minimal stand-in matching the OllamaChat duck type used by extract."""

    def __init__(self, response_content: str, *, tokens_in: int = 5, tokens_out: int = 3) -> None:
        self._response = response_content
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self.last_call: dict | None = None
        self.calls = 0

    async def chat(self, *, system, user, response_schema=None):
        self.calls += 1
        self.last_call = {"system": system, "user": user, "schema": response_schema}
        return ChatResult(
            content=self._response,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            model="m",
            provider="ollama",
        )


@pytest.mark.asyncio
async def test_extract_for_chunk_happy_path():
    payload = json.dumps(
        {
            "concepts": [{"name": "Caching"}, {"name": "Pricing"}],
            "relations": [
                {"from": "Caching", "relation": "depends_on", "to": "Pricing", "confidence": 0.9},
                {
                    "from": "Caching",
                    "relation": "invokes_magic",
                    "to": "Pricing",
                    "confidence": 0.9,
                },  # bad vocab
                {
                    "from": "Caching",
                    "relation": "depends_on",
                    "to": "Pricing",
                    "confidence": 0.4,
                },  # low
            ],
        }
    )
    chat = _FakeChat(payload, tokens_in=17, tokens_out=11)
    result, telemetry = await extract_for_chunk(
        chunk_text="some text",
        vocabulary=VOCAB,
        chat=chat,  # type: ignore[arg-type]
    )
    assert telemetry.parse_failed is False
    assert telemetry.tokens_in == 17
    assert telemetry.tokens_out == 11
    assert telemetry.raw_concepts == 2
    assert telemetry.raw_relations == 3
    assert telemetry.kept_relations == 1
    assert telemetry.dropped_unknown_vocab == 1
    assert telemetry.dropped_low_confidence == 1
    assert chat.last_call is not None
    # The vocabulary was passed in the prompt.
    assert "depends_on" in chat.last_call["system"]


@pytest.mark.asyncio
async def test_extract_for_chunk_parse_failure_raises():
    chat = _FakeChat("I cannot do this", tokens_in=3, tokens_out=4)
    with pytest.raises(ValueError, match="invalid JSON"):
        await extract_for_chunk(
            chunk_text="x",
            chunk_entity_id="chunk-1",
            vocabulary=VOCAB,
            chat=chat,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_extract_for_chunk_respects_timeout():
    class _SlowChat:
        async def chat(self, **kwargs):
            await asyncio.sleep(0.5)
            raise AssertionError("should have timed out")

    with pytest.raises(asyncio.TimeoutError):
        await extract_for_chunk(
            chunk_text="x",
            vocabulary=VOCAB,
            chat=_SlowChat(),  # type: ignore[arg-type]
            timeout_seconds=0.05,
        )
