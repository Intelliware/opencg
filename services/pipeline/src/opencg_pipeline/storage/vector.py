"""Qdrant client wrapper."""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models

from opencg_pipeline.util import reciprocal_rank_fusion


@dataclass
class VectorHit:
    entity_id: str
    score: float
    payload: dict
    collection: str | None = None


class VectorIndex:
    def __init__(
        self, *, url: str, collection_prefix: str, vector_size: int, distance: str = "cosine"
    ) -> None:
        self._client = AsyncQdrantClient(url=url)
        self._prefix = collection_prefix
        self._vector_size = vector_size
        self._distance = (
            models.Distance.COSINE if distance.lower() == "cosine" else models.Distance.DOT
        )

    def _collection(self, source: str) -> str:
        return f"{self._prefix}{source}"

    async def ensure_collection(self, source: str) -> None:
        coll = self._collection(source)
        if not await self._client.collection_exists(coll):
            await self._client.create_collection(
                collection_name=coll,
                vectors_config=models.VectorParams(size=self._vector_size, distance=self._distance),
            )

    async def upsert(
        self, *, source: str, entity_id: str, vector: list[float], payload: dict
    ) -> None:
        await self.ensure_collection(source)
        await self._client.upsert(
            collection_name=self._collection(source),
            points=[
                models.PointStruct(id=entity_id, vector=vector, payload=payload),
            ],
        )

    async def search(
        self,
        *,
        sources: list[str] | None,
        vector: list[float],
        limit: int,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        # Iterate per source — in the thin MVP we keep one collection per source
        # and rank-fuse across them. A future change consolidates to a single
        # collection with a payload filter on `source`.
        hits: list[VectorHit] = []
        targets = sources or [c.name for c in (await self._client.get_collections()).collections]
        for src in targets:
            coll = src if src.startswith(self._prefix) else self._collection(src)
            if not await self._client.collection_exists(coll):
                continue
            qfilter = self._build_filter(filters)
            results = await self._client.query_points(
                collection_name=coll,
                query=vector,
                limit=limit,
                query_filter=qfilter,
            )
            for p in results.points:
                hits.append(
                    VectorHit(
                        entity_id=str(p.id),
                        score=float(p.score),
                        payload=dict(p.payload or {}),
                        collection=coll,
                    )
                )
        # Truncate after the cross-source merge.
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    async def search_all(
        self,
        *,
        vector: list[float],
        limit: int,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        """Cross-collection search with RRF fusion.

        Used by the admin-side `/search/vector` endpoint. Queries every
        collection matching the configured prefix (or every collection if no
        prefix), gathers per-collection rankings, fuses with Reciprocal Rank
        Fusion, then attaches the fused score and returns the top `limit`.
        """
        all_collections = (await self._client.get_collections()).collections
        target_names = [
            c.name for c in all_collections if not self._prefix or c.name.startswith(self._prefix)
        ]

        qfilter = self._build_filter(filters)
        rankings: list[list[str]] = []
        # Keep a hit lookup so we can rebuild the merged payload/collection at
        # the end without a second round-trip.
        lookup: dict[str, VectorHit] = {}
        for coll in target_names:
            results = await self._client.query_points(
                collection_name=coll,
                query=vector,
                limit=limit,
                query_filter=qfilter,
            )
            ranking: list[str] = []
            for p in results.points:
                eid = str(p.id)
                ranking.append(eid)
                # First hit wins for payload/collection (it has the highest
                # per-collection score for that point).
                if eid not in lookup:
                    lookup[eid] = VectorHit(
                        entity_id=eid,
                        score=float(p.score),
                        payload=dict(p.payload or {}),
                        collection=coll,
                    )
            if ranking:
                rankings.append(ranking)

        fused = reciprocal_rank_fusion(rankings)
        merged: list[VectorHit] = []
        for eid, fused_score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True):
            hit = lookup[eid]
            hit.score = fused_score
            merged.append(hit)
        return merged[:limit]

    def _build_filter(self, filters: dict | None) -> models.Filter | None:
        if not filters:
            return None
        must: list[models.Condition] = []
        for k, v in filters.items():
            if isinstance(v, list):
                must.append(models.FieldCondition(key=k, match=models.MatchAny(any=list(v))))
            else:
                must.append(models.FieldCondition(key=k, match=models.MatchValue(value=v)))
        return models.Filter(must=must)

    async def collection_snapshot_id(self, source: str) -> str | None:
        """Return the current snapshot id for the source collection if any."""
        coll = self._collection(source)
        try:
            snaps = await self._client.list_snapshots(collection_name=coll)
            if snaps:
                return snaps[-1].name
        except Exception:
            return None
        return None

    async def close(self) -> None:
        await self._client.close()
