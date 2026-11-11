from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from opencg_pipeline.storage.vector import VectorIndex


@dataclass
class _Collection:
    name: str


@dataclass
class _Point:
    id: str
    score: float
    payload: dict[str, Any]


@dataclass
class _QueryResult:
    points: list[_Point]


class _Collections:
    def __init__(self, names: list[str]) -> None:
        self.collections = [_Collection(n) for n in names]


class _FakeQdrant:
    """Captures calls and returns canned per-collection rankings."""

    def __init__(self, *, collections: list[str], per_collection: dict[str, list[_Point]]) -> None:
        self._collections = collections
        self._per_collection = per_collection
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def get_collections(self) -> _Collections:
        return _Collections(self._collections)

    async def query_points(
        self, *, collection_name: str, query: list[float], limit: int, query_filter: Any = None
    ) -> _QueryResult:
        self.queries.append(
            (collection_name, {"query": query, "limit": limit, "filter": query_filter})
        )
        points = self._per_collection.get(collection_name, [])
        return _QueryResult(points=points[:limit])

    async def collection_exists(self, name: str) -> bool:
        return True


def _vi_with(fake: _FakeQdrant, prefix: str = "default__") -> VectorIndex:
    vi = VectorIndex(url="http://unused", collection_prefix=prefix, vector_size=4)
    vi._client = fake  # type: ignore[assignment]
    return vi


@pytest.mark.asyncio
async def test_search_all_only_queries_prefixed_collections():
    fake = _FakeQdrant(
        collections=["default__git", "default__confluence", "other__noise"],
        per_collection={
            "default__git": [_Point(id="g1", score=0.9, payload={"source": "git"})],
            "default__confluence": [_Point(id="c1", score=0.8, payload={"source": "confluence"})],
            "other__noise": [_Point(id="x1", score=1.0, payload={})],
        },
    )
    hits = await _vi_with(fake).search_all(vector=[0.1] * 4, limit=5)

    queried = [name for name, _ in fake.queries]
    assert "default__git" in queried and "default__confluence" in queried
    assert "other__noise" not in queried
    ids = [h.entity_id for h in hits]
    assert "x1" not in ids


@pytest.mark.asyncio
async def test_search_all_rrf_fuses_across_collections():
    # An entity appearing rank-1 in one collection AND rank-2 in another should
    # beat one that only shows up rank-1 in a single collection.
    fake = _FakeQdrant(
        collections=["default__git", "default__confluence"],
        per_collection={
            "default__git": [
                _Point(id="A", score=0.99, payload={"source": "git"}),
                _Point(id="B", score=0.50, payload={"source": "git"}),
            ],
            "default__confluence": [
                _Point(id="B", score=0.95, payload={"source": "confluence"}),
                _Point(id="A", score=0.40, payload={"source": "confluence"}),
            ],
        },
    )
    hits = await _vi_with(fake).search_all(vector=[0.0] * 4, limit=5)
    # A and B both rank 1 in one list and rank 2 in the other → equal fused scores;
    # both should beat anything from one list only.
    ids = [h.entity_id for h in hits]
    assert set(ids[:2]) == {"A", "B"}


@pytest.mark.asyncio
async def test_search_all_attaches_collection_and_payload():
    fake = _FakeQdrant(
        collections=["default__git"],
        per_collection={
            "default__git": [_Point(id="g1", score=0.9, payload={"title": "t", "text": "x"})],
        },
    )
    hits = await _vi_with(fake).search_all(vector=[0.0] * 4, limit=5)
    assert hits[0].collection == "default__git"
    assert hits[0].payload["title"] == "t"


@pytest.mark.asyncio
async def test_search_all_top_k_truncation():
    fake = _FakeQdrant(
        collections=["default__git"],
        per_collection={
            "default__git": [
                _Point(id=f"e{i}", score=1.0 / (i + 1), payload={}) for i in range(20)
            ],
        },
    )
    hits = await _vi_with(fake).search_all(vector=[0.0] * 4, limit=5)
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_all_with_filter_pushes_down():
    fake = _FakeQdrant(
        collections=["default__git"],
        per_collection={"default__git": [_Point(id="g1", score=0.9, payload={})]},
    )
    await _vi_with(fake).search_all(vector=[0.0] * 4, limit=5, filters={"source": "git"})
    _, kwargs = fake.queries[0]
    assert kwargs["filter"] is not None
