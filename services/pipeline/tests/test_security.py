"""Pipeline authentication, authorization and entitlement (add-identity-and-opa, task 4.9)."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx
import pytest
from authfakes import FakeOpa, authenticator, guarded_app, install
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from opencg_pipeline import app as app_module
from opencg_pipeline import security
from opencg_pipeline.graph import routes as graph_routes
from opencg_pipeline.providers import EmbeddingResult
from opencg_pipeline.storage.catalog import CatalogHit
from opencg_shared import openCGConfig
from opencg_shared.auth import hash_api_key
from opentelemetry.sdk.trace import TracerProvider

TRACER = TracerProvider().get_tracer("test")


# --- route coverage ---------------------------------------------------------------------


def _all_routes(routes, prefix: str = ""):
    """Every APIRoute, including those inside included routers (FastAPI 0.16x nests them)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router"):
            inner_prefix = prefix + getattr(route.include_context, "prefix", "")
            yield from _all_routes(route.original_router.routes, inner_prefix)


def _live_pairs() -> set[tuple[str, str]]:
    return {(m, p) for p, r in _all_routes(app_module.app.routes) for m in r.methods}


def test_every_route_has_an_action():
    missing = sorted(
        f"{m} {p}"
        for m, p in _live_pairs()
        if p not in security.OPEN_PATHS and (m, p) not in security.ROUTE_ACTIONS
    )
    assert missing == [], f"routes without an action in security.ROUTE_ACTIONS: {missing}"


def test_route_walk_sees_included_routers():
    assert ("POST", "/graph/edges/{edge_id}/promote") in _live_pairs()
    assert ("DELETE", "/entities/{entity_id}") in _live_pairs()


def test_action_table_has_no_stale_entries():
    assert set(security.ROUTE_ACTIONS) - _live_pairs() == set()


# --- retrieval ---------------------------------------------------------------------------


def _hit(eid: str, classification: str, chars: int = 400, score: float = 1.0) -> CatalogHit:
    return CatalogHit(
        entity_id=eid,
        source="git",
        source_uri=f"git://{eid}",
        title=eid,
        text="x" * chars,
        score=score,
        classification=classification,
    )


class _Catalog:
    def __init__(self, hits: list[CatalogHit]) -> None:
        self.hits = hits

    async def lexical_search(self, *, tenant: str, query: str, limit: int):
        return self.hits

    async def live_entity_ids(self, *, tenant: str, entity_ids: list[str]) -> set[str]:
        return set(entity_ids)


class _Vector:
    async def search(self, **_kwargs):
        return []


class _Embeddings:
    async def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(vector=[0.1], tokens_in=3, model="m", provider="ollama")


class _Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def write(self, row: dict[str, Any]) -> int:
        self.rows.append(row)
        return len(self.rows)


def _retrieval_client(*, hits, opa: FakeOpa, auth=None) -> tuple[TestClient, _Audit]:
    app = app_module.app
    audit = _Audit()
    app.state.cfg = openCGConfig()
    app.state.tracer = TRACER
    app.state.catalog = _Catalog(hits)
    app.state.vector = _Vector()
    app.state.embeddings = _Embeddings()
    app.state.audit = audit
    install(app, opa=opa, auth=auth)
    return TestClient(app, raise_server_exceptions=False), audit


def _body(principal="alice", roles=("admin", "legal"), budget=4000) -> dict[str, Any]:
    return {
        "correlation_id": "c-sec",
        "identity": {"principal": principal, "roles": list(roles), "tenant": "default"},
        "tool": "retrieve_for_context",
        "query": "q",
        "token_budget": budget,
    }


@pytest.fixture
def bob_key(tmp_path):
    raw = "ock_bob-key"
    f = tmp_path / "keys.json"
    f.write_text(
        json.dumps(
            [
                {
                    "name": "bob",
                    "key_sha256": hash_api_key(raw),
                    "principal": "bob",
                    "roles": ["reader"],
                }
            ]
        )
    )
    auth = authenticator(
        OPENCG__AUTH__MODE="oidc",
        OPENCG__AUTH__OIDC__ISSUER="http://idp/realms/opencg",
        OPENCG__AUTH__API_KEYS_FILE=str(f),
    )
    return auth, {"Authorization": f"Bearer {raw}"}


def test_token_identity_beats_body_identity(bob_key):
    auth, headers = bob_key
    opa = FakeOpa()
    client, audit = _retrieval_client(hits=[_hit("e1", "internal")], opa=opa, auth=auth)
    resp = client.post("/retrieve", json=_body(principal="alice", roles=["admin"]), headers=headers)
    assert resp.status_code == 200
    assert opa.entitle_calls[0]["principal"] == "bob"
    row = audit.rows[-1]
    assert row["principal"] == "bob"
    assert row["roles"] == ["reader"]
    assert row["auth_method"] == "api_key"


def test_missing_token_in_oidc_mode_is_401_without_audit():
    auth = authenticator(
        OPENCG__AUTH__MODE="oidc", OPENCG__AUTH__OIDC__ISSUER="http://idp/realms/opencg"
    )
    client, audit = _retrieval_client(hits=[], opa=FakeOpa(), auth=auth)
    resp = client.post("/retrieve", json=_body())
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "token_missing"
    assert audit.rows == []
    assert client.get("/healthz").status_code == 200


def test_none_mode_uses_body_identity_and_audits_none():
    client, audit = _retrieval_client(hits=[_hit("e1", "internal")], opa=FakeOpa())
    assert client.post("/retrieve", json=_body(principal="carol")).status_code == 200
    assert audit.rows[-1]["principal"] == "carol"
    assert audit.rows[-1]["auth_method"] == "none"


def test_denied_candidates_do_not_use_budget_and_one_policy_call():
    hits = [
        _hit("secret", "confidential:legal", chars=4000, score=3.0),  # ~1000 tokens, denied
        _hit("a", "internal", chars=2000, score=2.0),  # ~500
        _hit("b", "internal", chars=2000, score=1.0),  # ~500
    ]
    opa = FakeOpa(deny_classifications={"confidential:legal"})
    client, audit = _retrieval_client(hits=hits, opa=opa)
    resp = client.post("/retrieve", json=_body(budget=1000))
    assert resp.status_code == 200
    assert {f["entity_id"] for f in resp.json()["fragments"]} == {"a", "b"}
    assert len(opa.entitle_calls) == 1
    decisions = {d["entity_id"]: d for d in audit.rows[-1]["candidate_decisions"]}
    assert decisions["secret"]["decision"] == "deny"
    assert decisions["secret"]["policy_revision"] == "rev-test"
    assert decisions["secret"]["policy_package"] == "opencg.entitlement"
    assert decisions["a"]["decision"] == "include"


def test_budget_drop_and_deny_are_distinguishable():
    hits = [
        _hit("d", "confidential:legal", score=3.0),
        _hit("i", "internal", chars=2000, score=2.0),
        _hit("x", "internal", chars=4000, score=1.0),
    ]
    client, audit = _retrieval_client(
        hits=hits, opa=FakeOpa(deny_classifications={"confidential:legal"})
    )
    client.post("/retrieve", json=_body(budget=600))
    kinds = {d["entity_id"]: d["decision"] for d in audit.rows[-1]["candidate_decisions"]}
    assert kinds == {"d": "deny", "i": "include", "x": "drop"}


@pytest.mark.parametrize("where", ["guard", "entitle"])
def test_policy_unavailable_fails_closed_with_error_audit_row(where):
    opa = FakeOpa(unavailable=where == "guard", entitle_unavailable=where == "entitle")
    client, audit = _retrieval_client(hits=[_hit("e1", "internal")], opa=opa)
    resp = client.post("/retrieve", json=_body())
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "policy_unavailable"
    assert "fragments" not in resp.json()
    assert audit.rows[-1]["outcome"] == "error"
    assert audit.rows[-1]["error_code"] == "policy_unavailable"


def test_reader_forbidden_from_retrieve_is_audited():
    opa = FakeOpa(deny_actions={"retrieve"})
    client, audit = _retrieval_client(hits=[], opa=opa)
    resp = client.post("/retrieve", json=_body())
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "forbidden"
    assert audit.rows == []
    assert client.app.state.audit_pool.actions() == [("local-dev", "retrieve", "deny")]


# --- graph writes and access audit --------------------------------------------------------


class _Graph:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def transition_edge(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "edge_id": kwargs["edge_id"],
            "tenant": "default",
            "from_concept_id": "c1",
            "to_concept_id": "c2",
            "type": "depends_on",
            "state": kwargs["state"],
            "confidence": 0.9,
            "evidence_uri": "x",
            "extractor_version": "t",
            "created_at": "2026-11-12T00:00:00Z",
            "updated_at": "2026-11-12T00:00:00Z",
            "reason": kwargs.get("reason"),
        }


def _graph_client(opa: FakeOpa) -> tuple[TestClient, _Graph]:
    app = guarded_app(opa=opa)
    app.include_router(graph_routes.router)
    app.state.cfg = openCGConfig()
    graph = _Graph()
    app.state.graph = graph
    return TestClient(app), graph


def test_reader_cannot_promote_edge():
    client, graph = _graph_client(FakeOpa(deny_actions={"graph.write"}))
    resp = client.post("/graph/edges/e1/promote", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == {"code": "forbidden", "reason": "forbidden"}
    assert graph.calls == []  # no change, so no graph_audit_log row
    assert client.app.state.audit_pool.actions() == [("local-dev", "graph.write", "deny")]


def test_allowed_write_records_the_real_actor():
    client, graph = _graph_client(FakeOpa())
    resp = client.post("/graph/edges/e1/promote", json={})
    assert resp.status_code == 200, resp.text
    assert graph.calls[0]["actor"] == "local-dev"
    # The fake graph store does not claim the pending row, so the guard writes it.
    assert client.app.state.audit_pool.actions() == [("local-dev", "graph.write", "allow")]


def test_reads_are_not_access_audited():
    client, _ = _graph_client(FakeOpa())
    client.app.state.graph.list_edges = _async_return({"items": [], "total": 0})
    client.get("/graph/edges")
    assert client.app.state.audit_pool.rows == []


def _async_return(value):
    async def fn(**_kwargs):
        return value

    return fn


@pytest.mark.asyncio
async def test_pending_row_is_written_in_the_callers_transaction():
    rows: list = []

    class Conn:
        async def execute(self, sql, *args):
            rows.append((sql, args))

    token = security._pending.set(
        {
            **dict.fromkeys(
                [
                    "correlation_id",
                    "service",
                    "principal",
                    "roles",
                    "tenant",
                    "auth_method",
                    "action",
                    "resource",
                    "decision",
                    "reason",
                    "policy_package",
                    "policy_revision",
                ],
                "x",
            )
        }
    )
    try:
        await security.insert_pending_access_row(Conn())
        assert security.take_pending_access_row() is None  # claimed exactly once
    finally:
        security._pending.reset(token)
    assert "access_audit_log" in rows[0][0]


# --- vector search and ingestion proxy ------------------------------------------------------


def test_vector_search_drops_unentitled_hits():
    from authfakes import guarded_app as _g  # noqa: F401
    from opencg_pipeline import admin_routes
    from opencg_pipeline.storage.vector import VectorHit

    class Vector:
        async def search_all(self, *, vector, limit, filters=None):
            return [
                VectorHit(
                    entity_id="ok",
                    score=0.9,
                    collection="c",
                    payload={"classification": "internal", "source": "git"},
                ),
                VectorHit(
                    entity_id="legal",
                    score=0.8,
                    collection="c",
                    payload={"classification": "confidential:legal", "source": "git"},
                ),
            ]

    class Tracer:
        attributes: ClassVar[dict] = {}

        def start_as_current_span(self, name, **_kw):
            outer = self

            class S:
                def __enter__(self):
                    return self

                def __exit__(self, *e):
                    return None

                def set_attribute(self, k, v):
                    outer.attributes[k] = v

            return S()

    app = guarded_app(opa=FakeOpa(deny_classifications={"confidential:legal"}))
    app.include_router(admin_routes.router)
    app.state.cfg = openCGConfig()
    app.state.tracer = Tracer()
    app.state.vector = Vector()
    app.state.embeddings = _Embeddings()
    app.state.catalog = _Catalog([])
    resp = TestClient(app).post("/search/vector", json={"query": "q", "top_k": 5})
    assert resp.status_code == 200, resp.text
    assert [h["entity_id"] for h in resp.json()["hits"]] == ["ok"]
    assert Tracer.attributes["entitlement_filtered"] == 1


def test_ingestion_proxy_forwards_the_callers_token(bob_key):
    from opencg_pipeline import admin_routes

    auth, headers = bob_key
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(403, json={"detail": {"code": "forbidden"}})

    app = guarded_app(auth=auth)
    app.include_router(admin_routes.router)
    app.state.cfg = openCGConfig()
    app.state.ingestion_client = httpx.AsyncClient(
        base_url="http://ingestion", transport=httpx.MockTransport(handler)
    )
    resp = TestClient(app).get("/ingestion/connectors", headers=headers)
    assert seen["authorization"] == headers["Authorization"]
    assert resp.status_code == 403  # upstream 403 passes through
