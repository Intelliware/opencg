"""Concrete Ollama embeddings client. Hardcoded — no adapter abstraction yet
(introduced in a follow-up `model-providers` change)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from opencg_shared import pricing
from opencg_shared.metrics import record_provider_error
from opencg_shared.otel import current_correlation_id
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

_tracer = trace.get_tracer("opencg.providers")


def _error_code(exc: BaseException) -> str | None:
    """Provider error label: the HTTP status, `timeout`, or None (not a provider error)."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return str(exc.response.status_code)
    if isinstance(exc, httpx.TransportError):
        return "transport"
    return None


def _start_model_span(operation: str, provider: str, model: str):
    span = _tracer.start_span(f"model.{operation}")
    cid = current_correlation_id()
    if cid:
        span.set_attribute("correlation_id", cid)
    span.set_attribute("provider", provider)
    span.set_attribute("model", model)
    return span


def _finish_model_span(
    span, *, provider: str, model: str, tokens_in: int, tokens_out: int, t0: float
) -> float | None:
    cost = pricing.cost_usd(provider, model, tokens_in, tokens_out)
    span.set_attribute("tokens_in", tokens_in)
    span.set_attribute("tokens_out", tokens_out)
    span.set_attribute("latency_ms", int((time.perf_counter() - t0) * 1000))
    # -1 marks "unpriced" on the span (OTel attributes cannot be null).
    span.set_attribute("cost_usd", cost if cost is not None else -1.0)
    span.set_attribute("cost_priced", cost is not None)
    return cost


def _fail_model_span(span, provider: str, exc: BaseException) -> None:
    code = _error_code(exc)
    if code is not None:
        record_provider_error(provider, code)
        span.set_attribute("error_code", code)
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


@dataclass
class EmbeddingResult:
    vector: list[float]
    tokens_in: int
    model: str
    provider: str = "ollama"
    cost_usd: float | None = None


class _PathNotFound(Exception):
    """Internal sentinel: the server returned 404 for the endpoint we tried."""


class OllamaEmbeddings:
    """Embeddings via the Ollama REST API.

    Works against:
      * a local Ollama daemon (`http://ollama:11434` in compose, or
        `http://host.docker.internal:11434` when bridging to a host install)
      * Ollama Cloud (`https://ollama.com`) — note that the embed endpoint is
        gated on most accounts as of 2026-06; the client supports it but the
        thin-MVP deployment does not rely on Cloud for embeddings.
      * any OpenAI-style drop-in that mirrors the Ollama embed routes.

    Endpoint negotiation: the first request tries `/api/embed` (the newer route
    using `{"input":"…"}` → `{"embeddings":[[...]]}`); on a 404 the client
    falls back to `/api/embeddings` (legacy, `{"prompt":"…"}` →
    `{"embedding":[...]}`). The successful path is cached for the lifetime of
    the client to avoid double round-trips.

    When `api_key` is set the request adds `Authorization: Bearer <key>`. Local
    daemons ignore the header.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        provider: str = "ollama",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._provider = provider
        self._api_key = api_key or None
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)
        self._preferred_path: str | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

    async def embed(self, text: str) -> EmbeddingResult:
        span = _start_model_span("embed", self._provider, self._model)
        t0 = time.perf_counter()
        try:
            with trace.use_span(span, end_on_exit=False):
                vector = await self._embed_vector(text)
            tokens_in = max(1, len(text) // 4)
            cost = _finish_model_span(
                span,
                provider=self._provider,
                model=self._model,
                tokens_in=tokens_in,
                tokens_out=0,
                t0=t0,
            )
        except BaseException as exc:
            _fail_model_span(span, self._provider, exc)
            raise
        finally:
            span.end()
        return EmbeddingResult(
            vector=list(vector),
            tokens_in=tokens_in,
            model=self._model,
            provider=self._provider,
            cost_usd=cost,
        )

    async def _embed_vector(self, text: str) -> list[float]:
        if self._preferred_path is not None:
            vector = await self._call(self._preferred_path, text)
        else:
            try:
                vector = await self._call("/api/embed", text)
                self._preferred_path = "/api/embed"
            except _PathNotFound:
                vector = await self._call("/api/embeddings", text)
                self._preferred_path = "/api/embeddings"
        if vector is None:
            raise RuntimeError("Ollama returned no embedding")
        return vector

    async def _call(self, path: str, text: str) -> list[float] | None:
        if path == "/api/embed":
            payload = {"model": self._model, "input": text}
        else:
            payload = {"model": self._model, "prompt": text}
        resp = await self._client.post(f"{self._base}{path}", json=payload)
        if resp.status_code == 404:
            raise _PathNotFound(path)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body.get("embedding"), list):
            return body["embedding"]
        embs = body.get("embeddings")
        if embs:
            return embs[0]
        return None

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Chat client
# ---------------------------------------------------------------------------


@dataclass
class ChatResult:
    content: str
    tokens_in: int
    tokens_out: int
    model: str
    provider: str = "ollama"
    cost_usd: float | None = None


class OllamaChat:
    """Chat completion via Ollama's `/api/chat`.

    Used by the LLM extractor in `add-knowledge-graph` to produce
    structured JSON from a chunk's text. Works against:

      * a local Ollama daemon (e.g. `http://ollama:11434`)
      * Ollama Cloud (`https://ollama.com`)
      * any OpenAI-compatible Ollama-shaped drop-in

    Behaviour:
    - `Authorization: Bearer <key>` is added when `api_key` is non-empty.
    - When a `response_schema` is passed to `chat()`, the outbound body
      includes `"format": "json"` so the model returns parseable JSON.
    - `tokens_in` / `tokens_out` come from the response's
      `prompt_eval_count` / `eval_count` (the Ollama wire convention).
      When those fields are absent the counts fall back to character-based
      estimates so callers always get a usable integer.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        provider: str = "ollama",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._provider = provider
        self._api_key = api_key or None
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

    async def chat(
        self,
        *,
        system: str | None,
        user: str,
        response_schema: dict | None = None,
    ) -> ChatResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        body: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if response_schema is not None:
            body["format"] = "json"
        span = _start_model_span("chat", self._provider, self._model)
        t0 = time.perf_counter()
        try:
            with trace.use_span(span, end_on_exit=False):
                resp = await self._client.post(f"{self._base}/api/chat", json=body)
                resp.raise_for_status()
                data = resp.json()
            content = ((data.get("message") or {}).get("content") or "").strip()
            tokens_in = int(
                data.get("prompt_eval_count")
                or max(1, len(user) // 4 + (len(system) // 4 if system else 0))
            )
            tokens_out = int(data.get("eval_count") or max(1, len(content) // 4))
            cost = _finish_model_span(
                span,
                provider=self._provider,
                model=self._model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                t0=t0,
            )
        except BaseException as exc:
            _fail_model_span(span, self._provider, exc)
            raise
        finally:
            span.end()
        return ChatResult(
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=self._model,
            provider=self._provider,
            cost_usd=cost,
        )

    async def close(self) -> None:
        await self._client.aclose()
