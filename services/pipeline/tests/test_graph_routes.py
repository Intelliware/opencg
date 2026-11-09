from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opencg_pipeline.graph import routes
from opencg_shared import openCGConfig


def _concept(concept_id: str = "c1", state: str = "confirmed") -> dict:
    now = datetime(2026, 6, 12)
    return {
        "concept_id": concept_id,
        "tenant": "default",
        "name": f"Concept {concept_id}",
        "state": state,
        "confidence": 0.9,
        "aliases": [],
        "symbol_id": None,
        "symbol_kind": None,
        "updated_at": now,
        "tombstoned_at": None,
    }


def _edge(edge_id: str = "e1", state: str = "confirmed") -> dict:
    now = datetime(2026, 6, 12)
    return {
        "edge_id": edge_id,
        "tenant": "default",
        "type": "depends_on",
        "from_concept_id": "c1",
        "to_concept_id": "c2",
        "state": state,
        "confidence": 0.9,
        "extractor_version": "test",
        "created_at": now,
        "updated_at": now,
        "tombstoned_at": None,
    }


class FakeGraph:
    last: tuple[str, dict] | None = None
    concept_result: dict | None
    traverse_result: dict | None

    def __init__(self) -> None:
        self.concept_result = {
            **_concept(),
            "dedupe_key": "concept c1",
            "description": None,
            "extractor_version": "test",
            "source_entity_id": None,
            "created_at": datetime(2026, 6, 12),
            "neighbours_confirmed": [],
            "neighbours_candidate": [],
        }
        self.traverse_result = {
            "nodes": [_concept("c1"), _concept("c2")],
            "edges": [_edge()],
        }

    async def list_vocabulary(self):
        return [
            {
                "name": "depends_on",
                "description": "dependency",
                "inverse": None,
                "directed": True,
                "deprecated_at": None,
            }
        ]

    async def list_concepts(self, **kwargs):
        self.last = ("list_concepts", kwargs)
        return [_concept()], 1

    async def get_concept(self, **kwargs):
        self.last = ("get_concept", kwargs)
        return self.concept_result

    async def list_edges(self, **kwargs):
        self.last = ("list_edges", kwargs)
        return [_edge(state="candidate")], 1

    async def traverse(self, **kwargs):
        self.last = ("traverse", kwargs)
        return self.traverse_result

    async def transition_concept(self, **kwargs):
        self.last = ("transition_concept", kwargs)
        return {**_concept(kwargs["concept_id"], kwargs["state"]), "reason": kwargs["reason"]}

    async def patch_concept(self, **kwargs):
        self.last = ("patch_concept", kwargs)
        return {**_concept(kwargs["concept_id"]), **kwargs["changes"]}

    async def transition_edge(self, **kwargs):
        self.last = ("transition_edge", kwargs)
        return {**_edge(kwargs["edge_id"], kwargs["state"]), "reason": kwargs["reason"]}

    async def patch_edge(self, **kwargs):
        self.last = ("patch_edge", kwargs)
        return {**_edge(kwargs["edge_id"]), **kwargs["changes"]}

    async def create_vocabulary(self, **kwargs):
        self.last = ("create_vocabulary", kwargs)
        return {**kwargs["data"], "deprecated_at": None}

    async def patch_vocabulary(self, **kwargs):
        self.last = ("patch_vocabulary", kwargs)
        return {
            "name": kwargs["name"],
            "description": kwargs["changes"].get("description", ""),
            "inverse": None,
            "directed": True,
            "deprecated_at": None,
        }

    async def deprecate_vocabulary(self, **kwargs):
        self.last = ("deprecate_vocabulary", kwargs)
        return {
            "name": kwargs["name"],
            "description": "",
            "inverse": None,
            "directed": True,
            "deprecated_at": datetime(2026, 6, 12),
        }

    async def merge_concepts(self, **kwargs):
        self.last = ("merge_concepts", kwargs)
        return {
            **_concept(kwargs["into_id"]),
            "aliases": [f"Concept {item}" for item in kwargs["from_ids"]],
        }


def _client(graph: FakeGraph | None = None) -> tuple[TestClient, FakeGraph]:
    app = FastAPI()
    app.include_router(routes.router)
    app.state.cfg = openCGConfig()
    fake = graph or FakeGraph()
    app.state.graph = fake
    return TestClient(app), fake


def test_list_vocabulary():
    client, _ = _client()
    response = client.get("/graph/vocab")
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "depends_on"


def test_list_concepts_parses_filters():
    client, graph = _client()
    response = client.get(
        "/graph/concepts",
        params={"state": "candidate,confirmed", "search": "prompt", "limit": 10},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert graph.last == (
        "list_concepts",
        {
            "tenant": "default",
            "states": ["candidate", "confirmed"],
            "search": "prompt",
            "include_tombstoned": False,
            "limit": 10,
            "offset": 0,
        },
    )


def test_list_concepts_rejects_invalid_state():
    client, _ = _client()
    response = client.get("/graph/concepts", params={"state": "unknown"})
    assert response.status_code == 400


def test_get_concept_detail_and_not_found():
    graph = FakeGraph()
    client, _ = _client(graph)
    response = client.get("/graph/concepts/c1")
    assert response.status_code == 200
    assert response.json()["concept_id"] == "c1"

    graph.concept_result = None
    response = client.get("/graph/concepts/missing")
    assert response.status_code == 404


def test_list_candidate_edges():
    client, graph = _client()
    response = client.get(
        "/graph/edges",
        params={"state": "candidate", "type": "depends_on", "limit": 20},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["state"] == "candidate"
    assert graph.last == (
        "list_edges",
        {
            "tenant": "default",
            "state": "candidate",
            "relationship_type": "depends_on",
            "limit": 20,
            "offset": 0,
        },
    )


def test_traverse_and_concept_not_found():
    graph = FakeGraph()
    client, _ = _client(graph)
    response = client.get(
        "/graph/traverse",
        params={
            "concept_id": "c1",
            "types": "depends_on,mentions",
            "depth": 2,
            "include_candidates": True,
        },
    )
    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 2
    assert graph.last == (
        "traverse",
        {
            "tenant": "default",
            "concept_id": "c1",
            "types": ["depends_on", "mentions"],
            "depth": 2,
            "limit": 50,
            "include_candidates": True,
        },
    )

    graph.traverse_result = None
    response = client.get("/graph/traverse", params={"concept_id": "missing"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "concept_not_found"


def test_traverse_enforces_caps():
    client, _ = _client()
    assert client.get("/graph/traverse", params={"concept_id": "c1", "depth": 5}).status_code == 422
    assert (
        client.get("/graph/traverse", params={"concept_id": "c1", "limit": 201}).status_code == 422
    )


def test_concept_state_transitions_and_patch():
    client, graph = _client()
    response = client.post("/graph/concepts/c1/promote", json={"reason": "reviewed"})
    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"
    assert graph.last == (
        "transition_concept",
        {
            "tenant": "default",
            "concept_id": "c1",
            "state": "confirmed",
            "actor": "local-dev",
            "reason": "reviewed",
        },
    )

    response = client.patch(
        "/graph/concepts/c1",
        json={"description": "updated", "aliases": ["alias"], "reason": "cleanup"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "updated"
    assert graph.last[0] == "patch_concept"
    assert graph.last[1]["changes"] == {
        "description": "updated",
        "aliases": ["alias"],
    }


def test_edge_state_transitions_and_patch():
    client, graph = _client()
    response = client.post("/graph/edges/e1/demote", json={"reason": "uncertain"})
    assert response.status_code == 200
    assert response.json()["state"] == "candidate"
    assert graph.last[0] == "transition_edge"

    response = client.patch(
        "/graph/edges/e1",
        json={"type": "mentions", "reason": "corrected"},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "mentions"
    assert graph.last[0] == "patch_edge"
    assert graph.last[1]["changes"] == {"type": "mentions"}


def test_vocabulary_crud():
    client, graph = _client()
    response = client.post(
        "/graph/vocab",
        json={
            "name": "compatible_with",
            "description": "compatible",
            "directed": False,
        },
    )
    assert response.status_code == 201
    assert graph.last[0] == "create_vocabulary"

    response = client.patch(
        "/graph/vocab/compatible_with",
        json={"description": "updated"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "updated"

    response = client.post(
        "/graph/vocab/compatible_with/deprecate",
        json={"reason": "unused"},
    )
    assert response.status_code == 200
    assert response.json()["deprecated_at"] is not None


def test_merge_concepts():
    client, graph = _client()
    response = client.post(
        "/graph/concepts/merge",
        json={"into_id": "c1", "from_ids": ["c2", "c3"], "reason": "duplicates"},
    )
    assert response.status_code == 200
    assert response.json()["concept_id"] == "c1"
    assert graph.last == (
        "merge_concepts",
        {
            "tenant": "default",
            "into_id": "c1",
            "from_ids": ["c2", "c3"],
            "actor": "local-dev",
            "reason": "duplicates",
        },
    )
