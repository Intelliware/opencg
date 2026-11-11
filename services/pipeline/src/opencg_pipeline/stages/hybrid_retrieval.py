"""Stage 3 (thin MVP): hybrid retrieval = dense (Qdrant) + lexical (Postgres FTS),
fused with Reciprocal Rank Fusion.

In the thin MVP we skip Stage 2 (intent classification) and Stage 5 (rerank +
compress); the assemble stage handles the token budget directly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from opencg_pipeline.providers import OllamaEmbeddings
from opencg_pipeline.storage.catalog import CatalogHit, CatalogStore
from opencg_pipeline.storage.vector import VectorHit, VectorIndex
from opencg_pipeline.util import reciprocal_rank_fusion

__all__ = ["Candidate", "drop_tombstoned", "overfetch_limit", "reciprocal_rank_fusion", "run"]

_OVERFETCH_CAP = 200


def overfetch_limit(top_k: int) -> int:
    """How many vector hits to request so dropping tombstoned ones still leaves top_k."""
    return min(2 * top_k, max(top_k, _OVERFETCH_CAP))


async def drop_tombstoned(
    hits: list[VectorHit], *, catalog: CatalogStore, tenant: str, limit: int
) -> tuple[list[VectorHit], int]:
    """Keep hits whose catalogue row is live, in order, up to `limit`.

    Tombstoning only marks the Postgres row; the Qdrant point is unchanged.
    Returns (kept, number of tombstoned or missing hits dropped).
    """
    live = await catalog.live_entity_ids(tenant=tenant, entity_ids=[h.entity_id for h in hits])
    kept = [h for h in hits if h.entity_id in live]
    return kept[:limit], len(hits) - len(kept)


@dataclass
class Candidate:
    entity_id: str
    score: float
    source: str
    source_uri: str
    title: str | None
    text: str
    classification: str
    via: list[str]


async def run(
    *,
    tenant: str,
    query: str,
    top_k: int,
    catalog: CatalogStore,
    vector: VectorIndex,
    embeddings: OllamaEmbeddings,
) -> tuple[list[Candidate], dict]:
    """Returns (candidates, telemetry).

    telemetry includes per-leg latencies, model usage, vector_collection hit list.
    """

    # Dense leg: embed query, search Qdrant. Lexical leg: Postgres FTS+trgm.
    # Both run in parallel.
    async def dense_leg() -> tuple[list[VectorHit], int, int, str]:
        emb = await embeddings.embed(query)
        hits = await vector.search(sources=None, vector=emb.vector, limit=overfetch_limit(top_k))
        kept, dropped = await drop_tombstoned(hits, catalog=catalog, tenant=tenant, limit=top_k)
        return kept, dropped, emb.tokens_in, emb.model

    async def lexical_leg() -> list[CatalogHit]:
        return await catalog.lexical_search(tenant=tenant, query=query, limit=top_k)

    (
        (dense_hits, tombstoned_filtered, embed_tokens_in, embed_model),
        lexical_hits,
    ) = await asyncio.gather(dense_leg(), lexical_leg())

    dense_ranking = [h.entity_id for h in dense_hits]
    lexical_ranking = [h.entity_id for h in lexical_hits]
    fused = reciprocal_rank_fusion([dense_ranking, lexical_ranking])

    # Build a lookup over both result sets so we have full text + metadata.
    lookup: dict[str, Candidate] = {}
    for h in dense_hits:
        lookup[h.entity_id] = Candidate(
            entity_id=h.entity_id,
            score=fused.get(h.entity_id, 0.0),
            source=h.payload.get("source", "unknown"),
            source_uri=h.payload.get("source_uri", ""),
            title=h.payload.get("title"),
            text=h.payload.get("text", ""),
            classification=h.payload.get("classification", "internal"),
            via=["dense"],
        )
    for c in lexical_hits:
        if c.entity_id in lookup:
            lookup[c.entity_id].via.append("lexical")
            # Prefer Postgres text if Qdrant payload was missing it.
            if not lookup[c.entity_id].text:
                lookup[c.entity_id].text = c.text
                lookup[c.entity_id].title = c.title
            continue
        lookup[c.entity_id] = Candidate(
            entity_id=c.entity_id,
            score=fused.get(c.entity_id, 0.0),
            source=c.source,
            source_uri=c.source_uri,
            title=c.title,
            text=c.text,
            classification=c.classification,
            via=["lexical"],
        )

    candidates = sorted(lookup.values(), key=lambda c: c.score, reverse=True)[:top_k]

    telemetry = {
        "dense_count": len(dense_hits),
        "lexical_count": len(lexical_hits),
        "fused_count": len(candidates),
        "tombstoned_filtered": tombstoned_filtered,
        "embed_tokens_in": embed_tokens_in,
        "embed_model": embed_model,
    }
    return candidates, telemetry
