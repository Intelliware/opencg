"""Postgres-backed catalog access. Used by stage 3 (hybrid retrieval BM25)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import asyncpg

_AGE_SERVER_SETTINGS = {"search_path": 'ag_catalog, "$user", public'}


@dataclass
class CatalogHit:
    entity_id: str
    source: str
    source_uri: str
    title: str | None
    text: str
    score: float
    classification: str


class CatalogStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=1,
                max_size=8,
                server_settings=_AGE_SERVER_SETTINGS,
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("CatalogStore.connect() must be called first")
        return self._pool

    async def insert_entity(self, *, tenant: str, **row: Any) -> None:
        sql = """
        INSERT INTO opencg.entity (
          entity_id, tenant, source, source_uri, source_revision,
          parent_entity_id, title, body, content_hash, classification,
          owner, metadata
        ) VALUES (
          $1, $2, $3, $4, $5,
          $6, $7, $8, $9, $10,
          $11, $12
        )
        ON CONFLICT (tenant, source, source_uri) DO UPDATE SET
          body = EXCLUDED.body,
          title = EXCLUDED.title,
          content_hash = EXCLUDED.content_hash,
          classification = EXCLUDED.classification,
          owner = EXCLUDED.owner,
          metadata = EXCLUDED.metadata,
          source_revision = EXCLUDED.source_revision,
          updated_at = now(),
          last_verified_at = now(),
          freshness_state = 'fresh',
          tombstoned_at = NULL
        """
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                sql,
                row["entity_id"],
                tenant,
                row["source"],
                row["source_uri"],
                row.get("source_revision"),
                row.get("parent_entity_id"),
                row.get("title"),
                row["body"],
                row["content_hash"],
                row.get("classification", "internal"),
                row.get("owner"),
                json.dumps(row.get("metadata") or {}),
            )

    async def get_entity(self, *, tenant: str, entity_id: str) -> dict[str, Any] | None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT entity_id::text, source, source_uri, title, body,
                          classification, content_hash, metadata, updated_at
                   FROM opencg.entity
                   WHERE tenant = $1 AND entity_id = $2 AND tombstoned_at IS NULL""",
                tenant,
                entity_id,
            )
            return dict(row) if row else None

    async def list_entities(
        self,
        *,
        tenant: str,
        source: str | None = None,
        classification: str | None = None,
        freshness_state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Admin-side list with indexed filters. Returns (rows, total)."""
        pool = self._require_pool()
        # Build WHERE clause with optional filters; each filter only kicks in if
        # supplied, and they all reference indexed columns.
        clauses = ["tenant = $1"]
        params: list[Any] = [tenant]
        if source is not None:
            params.append(source)
            clauses.append(f"source = ${len(params)}")
        if classification is not None:
            params.append(classification)
            clauses.append(f"classification = ${len(params)}")
        if freshness_state is not None:
            params.append(freshness_state)
            clauses.append(f"freshness_state = ${len(params)}")
        where = " AND ".join(clauses)

        list_sql = f"""
        SELECT entity_id::text, tenant, source, source_uri, title,
               classification, freshness_state, updated_at, tombstoned_at
        FROM opencg.entity
        WHERE {where}
        ORDER BY updated_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        count_sql = f"SELECT count(*) FROM opencg.entity WHERE {where}"

        async with pool.acquire() as conn:
            rows = await conn.fetch(list_sql, *params, limit, offset)
            total = await conn.fetchval(count_sql, *params)
        return [dict(r) for r in rows], int(total or 0)

    async def get_entity_with_lineage(
        self, *, tenant: str, entity_id: str
    ) -> dict[str, Any] | None:
        """Single entity for the admin detail page (tombstoned rows included).

        Returns the entity columns plus a `lineage` block with parent (if any)
        and children (chunks under this entity, if any).
        """
        pool = self._require_pool()
        entity_sql = """
        SELECT entity_id::text, tenant, source, source_uri, source_revision,
               parent_entity_id::text, title, body, content_hash, classification,
               freshness_state, metadata, created_at, updated_at, ingested_at,
               last_verified_at, tombstoned_at
        FROM opencg.entity
        WHERE tenant = $1 AND entity_id = $2
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(entity_sql, tenant, entity_id)
            if row is None:
                return None
            data = dict(row)
            # metadata comes back as a JSON string from asyncpg — decode for the
            # response shape.
            if isinstance(data.get("metadata"), str):
                try:
                    data["metadata"] = json.loads(data["metadata"])
                except json.JSONDecodeError:
                    data["metadata"] = {}
            parent = None
            if data.get("parent_entity_id"):
                parent_row = await conn.fetchrow(
                    """SELECT entity_id::text, title, source_uri
                       FROM opencg.entity
                       WHERE tenant = $1 AND entity_id = $2""",
                    tenant,
                    data["parent_entity_id"],
                )
                if parent_row is not None:
                    parent = dict(parent_row)
            children = await conn.fetch(
                """SELECT entity_id::text, title, source_uri
                   FROM opencg.entity
                   WHERE tenant = $1 AND parent_entity_id = $2
                   ORDER BY (metadata->>'chunk_index')::int NULLS LAST, source_uri
                   LIMIT 500""",
                tenant,
                entity_id,
            )
            data["lineage"] = {
                "parent": parent,
                "children": [dict(c) for c in children],
            }
            return data

    async def tombstone(self, *, tenant: str, entity_id: str) -> dict[str, Any] | None:
        """Soft delete. Idempotent — re-tombstoning preserves the original timestamp."""
        pool = self._require_pool()
        sql = """
        UPDATE opencg.entity
        SET tombstoned_at = COALESCE(tombstoned_at, now())
        WHERE tenant = $1 AND entity_id = $2
        RETURNING entity_id::text, tenant, source, source_uri, title,
                  classification, freshness_state, updated_at, tombstoned_at
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant, entity_id)
        return dict(row) if row else None

    async def get_evidence_chunks(self, *, tenant: str, edge_id: str) -> list[dict[str, Any]]:
        """Return compact catalog references supporting a graph edge."""
        pool = self._require_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT entity.entity_id::text, entity.title, entity.source_uri
                FROM opencg.relationship_evidence evidence
                JOIN opencg.relationship_edge edge
                  ON edge.edge_id = evidence.edge_id
                JOIN opencg.entity entity
                  ON entity.entity_id = evidence.entity_id
                WHERE edge.tenant = $1 AND edge.edge_id = $2
                ORDER BY evidence.created_at, evidence.evidence_id
                """,
                tenant,
                edge_id,
            )
        return [dict(row) for row in rows]

    async def lexical_search(self, *, tenant: str, query: str, limit: int) -> list[CatalogHit]:
        """Postgres FTS + trigram fallback. The BM25-ish leg of hybrid retrieval."""
        pool = self._require_pool()
        sql = """
        WITH q AS (
          SELECT plainto_tsquery('simple', $2) AS tsq
        )
        SELECT entity_id::text, source, source_uri, title, body,
               classification,
               ts_rank_cd(
                 to_tsvector('simple', coalesce(title,'') || ' ' || body),
                 (SELECT tsq FROM q)
               ) AS rank
        FROM opencg.entity
        WHERE tenant = $1
          AND tombstoned_at IS NULL
          AND (
            to_tsvector('simple', coalesce(title,'') || ' ' || body) @@ (SELECT tsq FROM q)
            OR body % $2
            OR coalesce(title,'') % $2
          )
        ORDER BY rank DESC
        LIMIT $3
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, tenant, query, limit)
        return [
            CatalogHit(
                entity_id=r["entity_id"],
                source=r["source"],
                source_uri=r["source_uri"],
                title=r["title"],
                text=r["body"],
                score=float(r["rank"] or 0.0),
                classification=r["classification"],
            )
            for r in rows
        ]
