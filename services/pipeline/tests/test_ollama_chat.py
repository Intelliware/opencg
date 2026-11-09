from __future__ import annotations

import json

import pytest
import respx
from httpx import Response
from opencg_pipeline.providers import OllamaChat


@pytest.mark.asyncio
@respx.mock
async def test_chat_sends_bearer_when_api_key_set():
    route = respx.post("https://ollama.com/api/chat").mock(
        return_value=Response(
            200,
            json={
                "model": "gemma3:4b",
                "message": {"role": "assistant", "content": "hello"},
                "prompt_eval_count": 12,
                "eval_count": 5,
            },
        )
    )
    client = OllamaChat(base_url="https://ollama.com", model="gemma3:4b", api_key="secret-key")
    try:
        result = await client.chat(system="be helpful", user="hi")
    finally:
        await client.close()

    assert result.content == "hello"
    assert result.tokens_in == 12
    assert result.tokens_out == 5
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer secret-key"


@pytest.mark.asyncio
@respx.mock
async def test_chat_omits_auth_when_no_key():
    respx.post("http://ollama:11434/api/chat").mock(
        return_value=Response(
            200,
            json={"message": {"content": "ok"}, "prompt_eval_count": 1, "eval_count": 1},
        )
    )
    client = OllamaChat(base_url="http://ollama:11434", model="qwen2.5:7b")
    try:
        await client.chat(system=None, user="ping")
    finally:
        await client.close()

    sent = respx.calls[0].request
    assert "authorization" not in {k.lower() for k in sent.headers.keys()}


@pytest.mark.asyncio
@respx.mock
async def test_chat_format_json_when_response_schema_supplied():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return Response(
            200,
            json={"message": {"content": '{"ok":true}'}, "prompt_eval_count": 3, "eval_count": 2},
        )

    respx.post("https://ollama.com/api/chat").mock(side_effect=handler)
    client = OllamaChat(base_url="https://ollama.com", model="gemma3:4b")
    try:
        await client.chat(
            system="json only",
            user="emit",
            response_schema={"type": "object"},
        )
    finally:
        await client.close()

    assert captured["body"]["format"] == "json"
    # The schema itself isn't forwarded — Ollama's `format=json` is a
    # boolean toggle, not a schema-conditioned mode.


@pytest.mark.asyncio
@respx.mock
async def test_chat_propagates_http_errors():
    respx.post("https://ollama.com/api/chat").mock(
        return_value=Response(401, json={"error": "unauthorized"})
    )
    client = OllamaChat(base_url="https://ollama.com", model="m", api_key="bad")
    try:
        with pytest.raises(Exception):
            await client.chat(system=None, user="hi")
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_chat_falls_back_token_counts_when_missing():
    respx.post("http://ollama:11434/api/chat").mock(
        return_value=Response(
            200,
            json={"message": {"content": "small answer"}},  # no counts
        )
    )
    client = OllamaChat(base_url="http://ollama:11434", model="m")
    try:
        result = await client.chat(system=None, user="hello there")
    finally:
        await client.close()
    assert result.tokens_in >= 1
    assert result.tokens_out >= 1
