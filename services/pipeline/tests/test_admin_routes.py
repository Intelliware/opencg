"""Endpoint tests for admin_routes.

We mount the router on a fresh FastAPI app and stub `request.app.state` so the
endpoints don't need real Postgres/Qdrant/Ollama. This isolates routing,
parameter binding, error handling, and response shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opencg_pipeline import admin_routes
from opencg_pipeline.providers import EmbeddingResult
from opencg_pipeline.storage.vector import VectorHit
from opencg_shared import openCGConfig

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeCatalog:
    list_result: tuple[list[dict[str, Any]], int] = (
        [
            {
                "entity_id": "e1",
                "tenant": "default",
                "source": "git",
                "source_uri": "git://x/y",
                "title": "y",
                "classification": "internal",
                "freshness_state": "fresh",
                "updated_at": datetime(2026, 6, 11),
                "tombstoned_at": None,
            }
        ],
        1,
    )
    get_result: dict[str, Any] | None = None
    tombstone_result: dict[str, Any] | None = None
    last_list_kwargs: dict[str, Any] | None = None
    tombstoned: frozenset[str] = frozenset()

    async def list_entities(self, **kwargs):
        self.last_list_kwargs = kwargs
        return self.list_result

    async def get_entity_with_lineage(self, *, tenant: str, entity_id: str):
        return self.get_result

    async def tombstone(self, *, tenant: str, entity_id: str):
        return self.tombstone_result

    async def live_entity_ids(self, *, tenant: str, entity_ids: list[str]) -> set[str]:
        return {eid for eid in entity_ids if eid not in self.tombstoned}


@dataclass
class FakeEmbeddings:
    async def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(vector=[0.1, 0.2], tokens_in=7, model="m", provider="ollama")


@dataclass
class FakeVector:
    hits: list[VectorHit]
    last_limit: int | None = None

    async def search_all(self, *, vector, limit, filters=None):
        self.last_limit = limit
        return self.hits[:limit]


@dataclass
class FakeAudit:
    appearances: list[dict[str, Any]]

    async def list_for_entity(self, *, tenant: str, entity_id: str, limit: int):
        return self.appearances[:limit]


class FakeTracer:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    class _Span:
        def __init__(self, attributes: dict[str, Any]) -> None:
            self._attributes = attributes

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def set_attribute(self, key, value):
            self._attributes[key] = value

    def start_as_current_span(self, name: str):
        return self._Span(self.attributes)


def _mount(
    *,
    catalog: FakeCatalog | None = None,
    vector: FakeVector | None = None,
    embeddings: FakeEmbeddings | None = None,
    ingestion_client: httpx.AsyncClient | None = None,
    audit: FakeAudit | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.state.cfg = openCGConfig()
    app.state.tracer = FakeTracer()
    app.state.catalog = catalog or FakeCatalog()
    app.state.vector = vector or FakeVector(hits=[])
    app.state.embeddings = embeddings or FakeEmbeddings()
    app.state.audit = audit or FakeAudit(appearances=[])
    if ingestion_client is not None:
        app.state.ingestion_client = ingestion_client
    return TestClient(app)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


def test_list_entities_default_pagination():
    catalog = FakeCatalog()
    client = _mount(catalog=catalog)

    resp = client.get("/entities")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["items"][0]["entity_id"] == "e1"
    assert catalog.last_list_kwargs["limit"] == 50
    assert catalog.last_list_kwargs["offset"] == 0
    assert catalog.last_list_kwargs["source"] is None


def test_list_entities_passes_filters_and_caps_limit():
    catalog = FakeCatalog(list_result=([], 0))
    client = _mount(catalog=catalog)

    resp = client.get(
        "/entities",
        params={
            "source": "git",
            "classification": "internal",
            "freshness_state": "fresh",
            "limit": 200,
            "offset": 10,
        },
    )

    assert resp.status_code == 200
    assert catalog.last_list_kwargs == {
        "tenant": "default",
        "source": "git",
        "classification": "internal",
        "freshness_state": "fresh",
        "limit": 200,
        "offset": 10,
    }


def test_list_entities_rejects_oversized_limit():
    client = _mount()
    resp = client.get("/entities", params={"limit": 999})
    assert resp.status_code == 422  # FastAPI validation


def test_get_entity_returns_lineage_and_audit_appearances():
    catalog = FakeCatalog(
        get_result={
            "entity_id": "p1",
            "tenant": "default",
            "source": "git",
            "source_uri": "git://x/file",
            "source_revision": "abc",
            "parent_entity_id": None,
            "title": "file",
            "body": "full body",
            "content_hash": "h",
            "classification": "internal",
            "freshness_state": "fresh",
            "metadata": {"path": "file"},
            "created_at": datetime(2026, 6, 11),
            "updated_at": datetime(2026, 6, 11),
            "ingested_at": datetime(2026, 6, 11),
            "last_verified_at": datetime(2026, 6, 11),
            "tombstoned_at": None,
            "lineage": {
                "parent": None,
                "children": [
                    {
                        "entity_id": "c1",
                        "title": "file (chunk 0)",
                        "source_uri": "git://x/file#chunk=0",
                    }
                ],
            },
        }
    )
    client = _mount(
        catalog=catalog,
        audit=FakeAudit(
            appearances=[
                {
                    "id": 12,
                    "created_at": datetime(2026, 6, 11),
                    "correlation_id": "corr-12",
                    "tool": "retrieve_for_context",
                    "query": "prompt caching",
                    "outcome": "ok",
                }
            ]
        ),
    )

    resp = client.get("/entities/p1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] == "p1"
    assert body["lineage"]["children"][0]["entity_id"] == "c1"
    assert body["lineage"]["parent"] is None
    assert body["audit_appearances"][0]["id"] == 12


def test_get_entity_404():
    client = _mount()
    resp = client.get("/entities/missing")
    assert resp.status_code == 404


def test_tombstone_returns_updated_row():
    catalog = FakeCatalog(
        tombstone_result={
            "entity_id": "e1",
            "tenant": "default",
            "source": "git",
            "source_uri": "git://x/y",
            "title": "y",
            "classification": "internal",
            "freshness_state": "fresh",
            "updated_at": datetime(2026, 6, 11),
            "tombstoned_at": datetime(2026, 6, 11),
        }
    )
    client = _mount(catalog=catalog)

    resp = client.delete("/entities/e1")

    assert resp.status_code == 200
    assert resp.json()["tombstoned_at"] is not None


def test_tombstone_404():
    client = _mount()  # tombstone_result is None by default
    resp = client.delete("/entities/missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------


def test_vector_search_happy_path():
    vector = FakeVector(
        hits=[
            VectorHit(
                entity_id="g1",
                score=0.99,
                payload={
                    "source": "git",
                    "source_uri": "git://x/y",
                    "title": "y",
                    "text": "this is a snippet" * 5,
                    "classification": "internal",
                },
                collection="default__git",
            )
        ]
    )
    client = _mount(vector=vector)

    resp = client.post("/search/vector", json={"query": "hello", "top_k": 10})

    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "m"
    assert body["provider"] == "ollama"
    assert body["tokens_in"] == 7
    assert body["hits"][0]["entity_id"] == "g1"
    assert body["hits"][0]["collection"] == "default__git"
    # Snippet is normalised and length-capped.
    assert "snippet" in body["hits"][0]


def _vhit(eid: str, score: float) -> VectorHit:
    return VectorHit(
        entity_id=eid,
        score=score,
        payload={"source": "git", "source_uri": f"git://x/{eid}", "text": eid},
        collection="default__git",
    )


def test_vector_search_drops_tombstoned_entities():
    vector = FakeVector(hits=[_vhit("live", 0.9), _vhit("dead", 0.8)])
    client = _mount(vector=vector, catalog=FakeCatalog(tombstoned=frozenset({"dead"})))

    resp = client.post("/search/vector", json={"query": "hello", "top_k": 10})

    assert resp.status_code == 200
    assert [h["entity_id"] for h in resp.json()["hits"]] == ["live"]
    assert client.app.state.tracer.attributes["tombstoned_filtered"] == 1


def test_vector_search_refills_top_k_from_the_overfetch():
    hits = [_vhit(f"e{i:02d}", 1 - i / 100) for i in range(20)]
    tombstoned = frozenset({"e01", "e04", "e07"})
    vector = FakeVector(hits=hits)
    client = _mount(vector=vector, catalog=FakeCatalog(tombstoned=tombstoned))

    resp = client.post("/search/vector", json={"query": "hello", "top_k": 10})

    ids = [h["entity_id"] for h in resp.json()["hits"]]
    assert vector.last_limit == 20
    assert len(ids) == 10
    assert not tombstoned & set(ids)
    assert ids == sorted(ids)  # score order preserved


def test_vector_search_rejects_top_k_cap_violation():
    client = _mount()
    resp = client.post("/search/vector", json={"query": "x", "top_k": 500})
    assert resp.status_code == 422


def test_vector_search_rejects_empty_query():
    client = _mount()
    resp = client.post("/search/vector", json={"query": "", "top_k": 5})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Ingestion proxies
# ---------------------------------------------------------------------------


def _ingestion_client_with(handler):
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(base_url="http://upstream", transport=transport, timeout=5.0)


def test_proxy_connectors_pass_through():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/connectors"
        return httpx.Response(200, json=[{"name": "git", "supported": True}])

    client = _mount(ingestion_client=_ingestion_client_with(handler))
    resp = client.get("/ingestion/connectors")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "git", "supported": True}]


def test_proxy_run_git_forwards_body():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.content
        return httpx.Response(200, json={"run_id": "r1", "status": "queued"})

    client = _mount(ingestion_client=_ingestion_client_with(handler))
    resp = client.post("/ingestion/git/run", json={"repo_url": "https://github.com/a/b"})
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "status": "queued"}
    assert captured["path"] == "/run/git"
    assert b"repo_url" in captured["body"]


def test_proxy_runs_recent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"run_id": "r1", "status": "succeeded"}])

    client = _mount(ingestion_client=_ingestion_client_with(handler))
    resp = client.get("/ingestion/runs/recent")
    assert resp.status_code == 200
    assert resp.json() == [{"run_id": "r1", "status": "succeeded"}]


def test_proxy_translates_upstream_500_to_502():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _mount(ingestion_client=_ingestion_client_with(handler))
    resp = client.get("/ingestion/connectors")
    assert resp.status_code == 502
    assert resp.json()["detail"]["upstream_status"] == 500


def test_proxy_translates_unreachable_to_502():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    client = _mount(ingestion_client=_ingestion_client_with(handler))
    resp = client.post("/ingestion/git/run", json={"repo_url": "https://x"})
    assert resp.status_code == 502
    assert resp.json()["detail"]["upstream"] == "unreachable"


def test_proxy_forwards_4xx_as_is():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad repo url"})

    client = _mount(ingestion_client=_ingestion_client_with(handler))
    resp = client.post("/ingestion/git/run", json={"repo_url": "not-a-url"})
    assert resp.status_code == 400
