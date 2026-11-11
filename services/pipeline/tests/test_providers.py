from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response
from opencg_pipeline.providers import OllamaEmbeddings


@pytest.mark.asyncio
@respx.mock
async def test_embed_uses_new_endpoint_by_default():
    route = respx.post("http://ollama:11434/api/embed").mock(
        return_value=Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
    )
    client = OllamaEmbeddings(base_url="http://ollama:11434", model="nomic-embed-text")
    try:
        result = await client.embed("hello")
    finally:
        await client.close()

    assert result.vector == [0.1, 0.2, 0.3]
    assert result.model == "nomic-embed-text"
    assert route.called
    body = route.calls[0].request.read()
    assert b'"input": "hello"' in body or b'"input":"hello"' in body


@pytest.mark.asyncio
@respx.mock
async def test_embed_falls_back_to_legacy_on_404():
    new_route = respx.post("http://ollama:11434/api/embed").mock(
        return_value=Response(404, json={"error": "not found"})
    )
    legacy_route = respx.post("http://ollama:11434/api/embeddings").mock(
        return_value=Response(200, json={"embedding": [0.5, 0.6]})
    )
    client = OllamaEmbeddings(base_url="http://ollama:11434", model="legacy")
    try:
        result = await client.embed("hi")
    finally:
        await client.close()

    assert result.vector == [0.5, 0.6]
    assert new_route.called
    assert legacy_route.called
    body = legacy_route.calls[0].request.read()
    assert b'"prompt": "hi"' in body or b'"prompt":"hi"' in body


@pytest.mark.asyncio
@respx.mock
async def test_embed_caches_legacy_path_after_fallback():
    new_route = respx.post("http://ollama:11434/api/embed").mock(
        return_value=Response(404, json={"error": "not found"})
    )
    legacy_route = respx.post("http://ollama:11434/api/embeddings").mock(
        return_value=Response(200, json={"embedding": [0.0]})
    )
    client = OllamaEmbeddings(base_url="http://ollama:11434", model="legacy")
    try:
        await client.embed("first")
        await client.embed("second")
    finally:
        await client.close()

    assert new_route.call_count == 1
    assert legacy_route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_embed_sends_bearer_when_api_key_set():
    route = respx.post("https://ollama.com/api/embed").mock(
        return_value=Response(200, json={"embeddings": [[0.1]]})
    )
    client = OllamaEmbeddings(
        base_url="https://ollama.com",
        model="nomic-embed-text",
        api_key="secret-key",
    )
    try:
        await client.embed("hello")
    finally:
        await client.close()

    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer secret-key"


@pytest.mark.asyncio
@respx.mock
async def test_embed_omits_auth_when_no_key():
    respx.post("http://localhost:11434/api/embed").mock(
        return_value=Response(200, json={"embeddings": [[0.0]]})
    )
    client = OllamaEmbeddings(base_url="http://localhost:11434", model="nomic-embed-text")
    try:
        await client.embed("hi")
    finally:
        await client.close()

    sent = respx.calls[0].request
    assert "authorization" not in {k.lower() for k in sent.headers.keys()}


@pytest.mark.asyncio
@respx.mock
async def test_embed_propagates_non_404_errors():
    respx.post("https://ollama.com/api/embed").mock(
        return_value=Response(401, json={"error": "unauthorized"})
    )
    client = OllamaEmbeddings(base_url="https://ollama.com", model="m", api_key="bad")
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.embed("hi")
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_embed_handles_legacy_shape_from_new_endpoint():
    # Some older Ollama servers respond at /api/embed but return the legacy
    # {"embedding": [...]} body. The client must tolerate that.
    respx.post("http://ollama:11434/api/embed").mock(
        return_value=Response(200, json={"embedding": [9.0, 8.0]})
    )
    client = OllamaEmbeddings(base_url="http://ollama:11434", model="m")
    try:
        r = await client.embed("hi")
    finally:
        await client.close()
    assert r.vector == [9.0, 8.0]
