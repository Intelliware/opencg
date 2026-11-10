from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from opencg_pipeline.stages import hybrid_retrieval
from opencg_pipeline.storage.catalog import CatalogHit
from opencg_pipeline.storage.vector import VectorHit


@dataclass
class _Embedding:
    vector: list[float]
    tokens_in: int = 3
    model: str = "nomic-embed-text"


class _Embeddings:
    async def embed(self, text: str) -> _Embedding:
        return _Embedding(vector=[0.1, 0.2])


class _Vector:
    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits
        self.limits: list[int] = []

    async def search(self, *, sources: Any, vector: list[float], limit: int) -> list[VectorHit]:
        self.limits.append(limit)
        return self._hits[:limit]


class _Catalog:
    def __init__(self, *, tombstoned: set[str], lexical: list[CatalogHit] | None = None) -> None:
        self._tombstoned = tombstoned
        self._lexical = lexical or []

    async def live_entity_ids(self, *, tenant: str, entity_ids: list[str]) -> set[str]:
        return {eid for eid in entity_ids if eid not in self._tombstoned}

    async def lexical_search(self, *, tenant: str, query: str, limit: int) -> list[CatalogHit]:
        return self._lexical


def _hit(eid: str, score: float) -> VectorHit:
    return VectorHit(
        entity_id=eid,
        score=score,
        payload={"source": "git", "source_uri": f"git://r/{eid}", "text": eid},
        collection="default__git",
    )


async def _run(vector: _Vector, catalog: _Catalog, top_k: int = 3):
    return await hybrid_retrieval.run(
        tenant="default",
        query="amber-context protocol",
        top_k=top_k,
        catalog=catalog,  # type: ignore[arg-type]
        vector=vector,  # type: ignore[arg-type]
        embeddings=_Embeddings(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_tombstoned_dense_hit_never_becomes_a_candidate():
    vector = _Vector([_hit("a", 0.9), _hit("dead", 0.8), _hit("b", 0.7), _hit("c", 0.6)])
    candidates, telemetry = await _run(vector, _Catalog(tombstoned={"dead"}))

    ids = [c.entity_id for c in candidates]
    assert "dead" not in ids
    assert ids == ["a", "b", "c"]
    assert telemetry["tombstoned_filtered"] == 1
    assert telemetry["dense_count"] == 3


@pytest.mark.asyncio
async def test_dense_leg_overfetches_to_refill_top_k():
    vector = _Vector([_hit(str(i), 1 - i / 10) for i in range(10)])
    await _run(vector, _Catalog(tombstoned=set()), top_k=3)
    assert vector.limits == [6]


@pytest.mark.asyncio
async def test_lexical_leg_is_unchanged():
    lexical = [
        CatalogHit(
            entity_id="lex",
            source="git",
            source_uri="git://r/lex",
            title=None,
            text="lexical only",
            score=1.0,
            classification="internal",
        )
    ]
    candidates, _ = await _run(_Vector([]), _Catalog(tombstoned=set(), lexical=lexical))
    assert [(c.entity_id, c.via) for c in candidates] == [("lex", ["lexical"])]


def test_overfetch_limit_is_capped_but_never_below_top_k():
    assert hybrid_retrieval.overfetch_limit(10) == 20
    assert hybrid_retrieval.overfetch_limit(150) == 200
    assert hybrid_retrieval.overfetch_limit(300) == 300
