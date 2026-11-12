"""Postgres + Apache AGE access for the knowledge graph."""

from __future__ import annotations

import json
import re
from typing import Any

import asyncpg
from opencg_shared.metrics import record_audit_write

from opencg_pipeline.graph.age import (
    delete_reflected_edge,
    reflect_concept,
    reflect_edge,
)

_RELATION_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_AGE_SERVER_SETTINGS = {"search_path": 'ag_catalog, "$user", public'}


class GraphStore:
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
            raise RuntimeError("GraphStore.connect() must be called first")
        return self._pool

    async def list_vocabulary(self) -> list[dict[str, Any]]:
        async with self._require_pool().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT name, description, inverse, directed, deprecated_at
                FROM opencg.relationship_vocab
                ORDER BY name
                """
            )
        return [dict(row) for row in rows]

    async def list_concepts(
        self,
        *,
        tenant: str,
        states: list[str],
        search: str | None,
        include_tombstoned: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses = ["tenant = $1"]
        params: list[Any] = [tenant]
        if states:
            params.append(states)
            clauses.append(f"state = ANY(${len(params)}::text[])")
        if not include_tombstoned:
            clauses.append("state <> 'tombstoned'")
        if search:
            params.append(f"%{search}%")
            clauses.append(f"name ILIKE ${len(params)}")
        where = " AND ".join(clauses)
        async with self._require_pool().acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT concept_id::text, tenant, name, state, confidence,
                       aliases, symbol_id, symbol_kind, updated_at, tombstoned_at
                FROM opencg.concept
                WHERE {where}
                ORDER BY updated_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params,
                limit,
                offset,
            )
            total = await conn.fetchval(
                f"SELECT count(*) FROM opencg.concept WHERE {where}",
                *params,
            )
        return [dict(row) for row in rows], int(total or 0)

    async def get_concept(self, *, tenant: str, concept_id: str) -> dict[str, Any] | None:
        async with self._require_pool().acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT concept_id::text, tenant, name, dedupe_key, description,
                       aliases, state, confidence, extractor_version,
                       source_entity_id::text, symbol_id, symbol_kind,
                       created_at, updated_at, tombstoned_at
                FROM opencg.concept
                WHERE tenant = $1 AND concept_id = $2
                """,
                tenant,
                concept_id,
            )
            if row is None:
                return None
            neighbours = await conn.fetch(
                """
                SELECT e.edge_id::text, e.tenant, e.type,
                       e.from_concept_id::text, e.to_concept_id::text,
                       e.state, e.confidence, e.extractor_version,
                       e.created_at, e.updated_at, e.tombstoned_at,
                       peer.concept_id::text AS peer_concept_id,
                       peer.tenant AS peer_tenant, peer.name AS peer_name,
                       peer.state AS peer_state, peer.confidence AS peer_confidence,
                       peer.aliases AS peer_aliases, peer.symbol_id AS peer_symbol_id,
                       peer.symbol_kind AS peer_symbol_kind,
                       peer.updated_at AS peer_updated_at,
                       peer.tombstoned_at AS peer_tombstoned_at,
                       COALESCE(array_agg(ev.entity_id::text)
                         FILTER (WHERE ev.entity_id IS NOT NULL), '{}') AS evidence_entity_ids
                FROM opencg.relationship_edge e
                JOIN opencg.concept peer
                  ON peer.concept_id = CASE
                    WHEN e.from_concept_id = $2 THEN e.to_concept_id
                    ELSE e.from_concept_id
                  END
                LEFT JOIN opencg.relationship_evidence ev ON ev.edge_id = e.edge_id
                WHERE e.tenant = $1
                  AND (e.from_concept_id = $2 OR e.to_concept_id = $2)
                  AND e.state <> 'tombstoned'
                  AND peer.state <> 'tombstoned'
                GROUP BY e.edge_id, peer.concept_id
                ORDER BY e.state, e.confidence DESC
                """,
                tenant,
                concept_id,
            )
        data = dict(row)
        data["neighbours_confirmed"] = []
        data["neighbours_candidate"] = []
        for item in neighbours:
            n = dict(item)
            neighbour = {
                "edge": {
                    key: n[key]
                    for key in (
                        "edge_id",
                        "tenant",
                        "type",
                        "from_concept_id",
                        "to_concept_id",
                        "state",
                        "confidence",
                        "extractor_version",
                        "created_at",
                        "updated_at",
                        "tombstoned_at",
                    )
                },
                "peer": {
                    "concept_id": n["peer_concept_id"],
                    "tenant": n["peer_tenant"],
                    "name": n["peer_name"],
                    "state": n["peer_state"],
                    "confidence": n["peer_confidence"],
                    "aliases": n["peer_aliases"],
                    "symbol_id": n["peer_symbol_id"],
                    "symbol_kind": n["peer_symbol_kind"],
                    "updated_at": n["peer_updated_at"],
                    "tombstoned_at": n["peer_tombstoned_at"],
                },
                "evidence_entity_ids": n["evidence_entity_ids"],
            }
            data[f"neighbours_{n['state']}"].append(neighbour)
        return data

    async def list_edges(
        self,
        *,
        tenant: str,
        state: str | None,
        relationship_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses = ["e.tenant = $1", "e.state <> 'tombstoned'"]
        params: list[Any] = [tenant]
        if state:
            params.append(state)
            clauses.append(f"e.state = ${len(params)}")
        if relationship_type:
            params.append(relationship_type)
            clauses.append(f"e.type = ${len(params)}")
        where = " AND ".join(clauses)
        async with self._require_pool().acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT e.edge_id::text, e.tenant, e.type,
                       e.from_concept_id::text, e.to_concept_id::text,
                       e.state, e.confidence, e.extractor_version,
                       e.created_at, e.updated_at, e.tombstoned_at,
                       COALESCE(array_agg(ev.entity_id::text)
                         FILTER (WHERE ev.entity_id IS NOT NULL), '{{}}') AS evidence_entity_ids
                FROM opencg.relationship_edge e
                LEFT JOIN opencg.relationship_evidence ev ON ev.edge_id = e.edge_id
                WHERE {where}
                GROUP BY e.edge_id
                ORDER BY e.confidence DESC, e.created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params,
                limit,
                offset,
            )
            total = await conn.fetchval(
                f"SELECT count(*) FROM opencg.relationship_edge e WHERE {where}",
                *params,
            )
        return [dict(row) for row in rows], int(total or 0)

    async def traverse(
        self,
        *,
        tenant: str,
        concept_id: str,
        types: list[str] | None,
        depth: int,
        limit: int,
        include_candidates: bool,
    ) -> dict[str, list[dict[str, Any]]] | None:
        async with self._require_pool().acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS(
                  SELECT 1 FROM opencg.concept
                  WHERE tenant = $1 AND concept_id = $2 AND state <> 'tombstoned'
                )
                """,
                tenant,
                concept_id,
            )
            if not exists:
                return None
            if types:
                vocab_rows = await conn.fetch(
                    """
                    SELECT name FROM opencg.relationship_vocab
                    WHERE name = ANY($1::text[])
                    """,
                    types,
                )
                valid_types = {row["name"] for row in vocab_rows}
                if valid_types != set(types):
                    raise ValueError("unknown relationship type")
                relation_pattern = ":" + "|".join(
                    sorted(_validated_relation(name) for name in valid_types)
                )
            else:
                relation_pattern = ""
            states = ["confirmed", "candidate"] if include_candidates else ["confirmed"]
            params = json.dumps(
                {
                    "concept_id": concept_id,
                    "candidate_limit": min(limit * 10, 2000),
                }
            )
            peer_rows = await conn.fetch(
                f"""
                SELECT concept_id
                FROM ag_catalog.cypher(
                  'opencg',
                  $cypher$
                    MATCH (start:Concept {{concept_id: $concept_id}})
                          -[edges{relation_pattern}*1..{depth}]-
                          (peer:Concept)
                    RETURN DISTINCT peer.concept_id
                    LIMIT $candidate_limit
                  $cypher$,
                  $1::ag_catalog.agtype
                ) AS (concept_id ag_catalog.agtype)
                """,
                params,
            )
            ids = [concept_id]
            ids.extend(_agtype_text(row["concept_id"]) for row in peer_rows)
            candidate_ids = list(dict.fromkeys(ids))
            candidate_nodes = await conn.fetch(
                """
                SELECT concept_id::text, tenant, name, state, confidence,
                       aliases, symbol_id, symbol_kind, updated_at, tombstoned_at
                FROM opencg.concept
                WHERE tenant = $1
                  AND concept_id = ANY($2::uuid[])
                  AND state <> 'tombstoned'
                """,
                tenant,
                candidate_ids,
            )
            node_by_id = {str(row["concept_id"]): dict(row) for row in candidate_nodes}
            active_ids = list(node_by_id)
            edge_rows = await conn.fetch(
                """
                SELECT edge_id::text, tenant, type, from_concept_id::text,
                       to_concept_id::text, state, confidence, extractor_version,
                       created_at, updated_at, tombstoned_at
                FROM opencg.relationship_edge
                WHERE tenant = $1
                  AND from_concept_id = ANY($2::uuid[])
                  AND to_concept_id = ANY($2::uuid[])
                  AND state = ANY($3::text[])
                  AND ($4::text[] IS NULL OR type = ANY($4::text[]))
                ORDER BY confidence DESC
                """,
                tenant,
                active_ids,
                states,
                types,
            )
            edges = [dict(row) for row in edge_rows]
            reachable_ids = _reachable_ids(
                concept_id=concept_id,
                edges=edges,
                depth=depth,
                limit=limit,
            )
            reachable_set = set(reachable_ids)
        return {
            "nodes": [node_by_id[node_id] for node_id in reachable_ids],
            "edges": [
                edge
                for edge in edges
                if edge["from_concept_id"] in reachable_set
                and edge["to_concept_id"] in reachable_set
            ],
        }

    async def transition_concept(
        self,
        *,
        tenant: str,
        concept_id: str,
        state: str,
        actor: str,
        reason: str | None,
    ) -> dict[str, Any] | None:
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT * FROM opencg.concept WHERE tenant = $1 AND concept_id = $2 FOR UPDATE",
                    tenant,
                    concept_id,
                )
                if before is None:
                    return None
                before_data = dict(before)
                if before_data["state"] == state:
                    return before_data
                row = await conn.fetchrow(
                    """
                    UPDATE opencg.concept
                    SET state = $3,
                        tombstoned_at = CASE WHEN $3 = 'tombstoned' THEN COALESCE(tombstoned_at, now()) ELSE NULL END,
                        updated_at = now()
                    WHERE tenant = $1 AND concept_id = $2
                    RETURNING *
                    """,
                    tenant,
                    concept_id,
                    state,
                )
                after = dict(row)
                await reflect_concept(
                    conn,
                    concept_id=str(after["concept_id"]),
                    tenant=tenant,
                    name=after["name"],
                    state=after["state"],
                )
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="concept",
                    target_id=concept_id,
                    from_state=before_data["state"],
                    to_state=state,
                    reason=reason,
                    before=before_data,
                    after=after,
                )
                return after

    async def patch_concept(
        self,
        *,
        tenant: str,
        concept_id: str,
        actor: str,
        reason: str | None,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed = {
            key: value
            for key, value in changes.items()
            if key in {"name", "description", "aliases"}
        }
        if not allowed:
            raise ValueError("no editable concept fields supplied")
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT * FROM opencg.concept WHERE tenant = $1 AND concept_id = $2 FOR UPDATE",
                    tenant,
                    concept_id,
                )
                if before is None:
                    return None
                current = dict(before)
                name = allowed.get("name", current["name"])
                dedupe_key = _normalise_name(name)
                row = await conn.fetchrow(
                    """
                    UPDATE opencg.concept
                    SET name = $3, dedupe_key = $4, description = $5,
                        aliases = $6, updated_at = now()
                    WHERE tenant = $1 AND concept_id = $2
                    RETURNING *
                    """,
                    tenant,
                    concept_id,
                    name,
                    dedupe_key,
                    allowed.get("description", current["description"]),
                    allowed.get("aliases", current["aliases"]),
                )
                after = dict(row)
                await reflect_concept(
                    conn,
                    concept_id=str(after["concept_id"]),
                    tenant=tenant,
                    name=after["name"],
                    state=after["state"],
                )
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="concept",
                    target_id=concept_id,
                    from_state=current["state"],
                    to_state=after["state"],
                    reason=reason or "concept patched",
                    before=current,
                    after=after,
                )
                return after

    async def transition_edge(
        self,
        *,
        tenant: str,
        edge_id: str,
        state: str,
        actor: str,
        reason: str | None,
    ) -> dict[str, Any] | None:
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT * FROM opencg.relationship_edge WHERE tenant = $1 AND edge_id = $2 FOR UPDATE",
                    tenant,
                    edge_id,
                )
                if before is None:
                    return None
                before_data = dict(before)
                if before_data["state"] == state:
                    return before_data
                row = await conn.fetchrow(
                    """
                    UPDATE opencg.relationship_edge
                    SET state = $3,
                        tombstoned_at = CASE WHEN $3 = 'tombstoned' THEN COALESCE(tombstoned_at, now()) ELSE NULL END,
                        updated_at = now()
                    WHERE tenant = $1 AND edge_id = $2
                    RETURNING *
                    """,
                    tenant,
                    edge_id,
                    state,
                )
                after = dict(row)
                await reflect_edge(
                    conn,
                    edge_id=str(after["edge_id"]),
                    tenant=tenant,
                    relationship_type=after["type"],
                    from_concept_id=str(after["from_concept_id"]),
                    to_concept_id=str(after["to_concept_id"]),
                    state=after["state"],
                    confidence=float(after["confidence"]),
                )
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="edge",
                    target_id=edge_id,
                    from_state=before_data["state"],
                    to_state=state,
                    reason=reason,
                    before=before_data,
                    after=after,
                )
                return after

    async def patch_edge(
        self,
        *,
        tenant: str,
        edge_id: str,
        actor: str,
        reason: str | None,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed = {
            key: value
            for key, value in changes.items()
            if key in {"type", "from_concept_id", "to_concept_id"}
        }
        if not allowed:
            raise ValueError("no editable edge fields supplied")
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT * FROM opencg.relationship_edge WHERE tenant = $1 AND edge_id = $2 FOR UPDATE",
                    tenant,
                    edge_id,
                )
                if before is None:
                    return None
                current = dict(before)
                relationship_type = allowed.get("type", current["type"])
                await _assert_active_vocab(conn, relationship_type)
                row = await conn.fetchrow(
                    """
                    UPDATE opencg.relationship_edge
                    SET type = $3, from_concept_id = $4, to_concept_id = $5,
                        updated_at = now()
                    WHERE tenant = $1 AND edge_id = $2
                    RETURNING *
                    """,
                    tenant,
                    edge_id,
                    relationship_type,
                    allowed.get("from_concept_id", current["from_concept_id"]),
                    allowed.get("to_concept_id", current["to_concept_id"]),
                )
                after = dict(row)
                await delete_reflected_edge(
                    conn,
                    edge_id=edge_id,
                    relationship_type=current["type"],
                )
                await reflect_edge(
                    conn,
                    edge_id=edge_id,
                    tenant=tenant,
                    relationship_type=after["type"],
                    from_concept_id=str(after["from_concept_id"]),
                    to_concept_id=str(after["to_concept_id"]),
                    state=after["state"],
                    confidence=float(after["confidence"]),
                )
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="edge",
                    target_id=edge_id,
                    from_state=current["state"],
                    to_state=after["state"],
                    reason=reason or "edge patched",
                    before=current,
                    after=after,
                )
                return after

    async def create_vocabulary(
        self,
        *,
        tenant: str,
        actor: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        name = _validated_relation(data["name"])
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT * FROM opencg.relationship_vocab WHERE name = $1",
                    name,
                )
                if existing is not None:
                    raise ValueError("vocab_name_in_use")
                row = await conn.fetchrow(
                    """
                    INSERT INTO opencg.relationship_vocab
                      (name, description, inverse, directed)
                    VALUES ($1, $2, $3, $4)
                    RETURNING *
                    """,
                    name,
                    data.get("description") or "",
                    data.get("inverse"),
                    data.get("directed", True),
                )
                after = dict(row)
                await conn.execute(
                    """
                    SELECT ag_catalog.create_elabel(
                      'opencg'::cstring,
                      $1::text::cstring
                    )
                    """,
                    name,
                )
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="vocab",
                    target_id=name,
                    from_state=None,
                    to_state="active",
                    reason="vocabulary created",
                    before=None,
                    after=after,
                )
                return after

    async def patch_vocabulary(
        self,
        *,
        tenant: str,
        name: str,
        actor: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT * FROM opencg.relationship_vocab WHERE name = $1 FOR UPDATE",
                    name,
                )
                if before is None:
                    return None
                current = dict(before)
                row = await conn.fetchrow(
                    """
                    UPDATE opencg.relationship_vocab
                    SET description = $2, inverse = $3, directed = $4
                    WHERE name = $1
                    RETURNING *
                    """,
                    name,
                    changes.get("description", current["description"]),
                    changes.get("inverse", current["inverse"]),
                    changes.get("directed", current["directed"]),
                )
                after = dict(row)
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="vocab",
                    target_id=name,
                    from_state="active" if current["deprecated_at"] is None else "deprecated",
                    to_state="active" if after["deprecated_at"] is None else "deprecated",
                    reason="vocabulary patched",
                    before=current,
                    after=after,
                )
                return after

    async def deprecate_vocabulary(
        self, *, tenant: str, name: str, actor: str, reason: str | None
    ) -> dict[str, Any] | None:
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                before = await conn.fetchrow(
                    "SELECT * FROM opencg.relationship_vocab WHERE name = $1 FOR UPDATE",
                    name,
                )
                if before is None:
                    return None
                current = dict(before)
                if current["deprecated_at"] is not None:
                    return current
                row = await conn.fetchrow(
                    """
                    UPDATE opencg.relationship_vocab
                    SET deprecated_at = now()
                    WHERE name = $1
                    RETURNING *
                    """,
                    name,
                )
                after = dict(row)
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="vocab",
                    target_id=name,
                    from_state="active",
                    to_state="deprecated",
                    reason=reason,
                    before=current,
                    after=after,
                )
                return after

    async def merge_concepts(
        self,
        *,
        tenant: str,
        into_id: str,
        from_ids: list[str],
        actor: str,
        reason: str | None,
    ) -> dict[str, Any] | None:
        source_ids = list(dict.fromkeys(item for item in from_ids if item != into_id))
        if not source_ids:
            raise ValueError("from_ids must contain a concept other than into_id")
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                into_row = await conn.fetchrow(
                    "SELECT * FROM opencg.concept WHERE tenant = $1 AND concept_id = $2 FOR UPDATE",
                    tenant,
                    into_id,
                )
                if into_row is None:
                    return None
                sources = await conn.fetch(
                    """
                    SELECT * FROM opencg.concept
                    WHERE tenant = $1 AND concept_id = ANY($2::uuid[])
                    FOR UPDATE
                    """,
                    tenant,
                    source_ids,
                )
                if len(sources) != len(source_ids):
                    raise ValueError("one or more merge source concepts were not found")

                edges = await conn.fetch(
                    """
                    SELECT * FROM opencg.relationship_edge
                    WHERE tenant = $1
                      AND (from_concept_id = ANY($2::uuid[])
                        OR to_concept_id = ANY($2::uuid[]))
                    FOR UPDATE
                    """,
                    tenant,
                    source_ids,
                )
                for edge_row in edges:
                    edge = dict(edge_row)
                    edge_id = str(edge["edge_id"])
                    new_from = (
                        into_id
                        if str(edge["from_concept_id"]) in source_ids
                        else str(edge["from_concept_id"])
                    )
                    new_to = (
                        into_id
                        if str(edge["to_concept_id"]) in source_ids
                        else str(edge["to_concept_id"])
                    )
                    duplicate = await conn.fetchrow(
                        """
                        SELECT * FROM opencg.relationship_edge
                        WHERE tenant = $1 AND from_concept_id = $2
                          AND type = $3 AND to_concept_id = $4
                          AND edge_id <> $5
                        FOR UPDATE
                        """,
                        tenant,
                        new_from,
                        edge["type"],
                        new_to,
                        edge_id,
                    )
                    await delete_reflected_edge(
                        conn,
                        edge_id=edge_id,
                        relationship_type=edge["type"],
                    )
                    if duplicate is not None:
                        duplicate_id = str(duplicate["edge_id"])
                        await conn.execute(
                            """
                            UPDATE opencg.relationship_evidence
                            SET edge_id = $1
                            WHERE edge_id = $2
                            """,
                            duplicate_id,
                            edge_id,
                        )
                        await conn.execute(
                            "DELETE FROM opencg.relationship_edge WHERE edge_id = $1",
                            edge_id,
                        )
                        continue
                    updated = await conn.fetchrow(
                        """
                        UPDATE opencg.relationship_edge
                        SET from_concept_id = $2, to_concept_id = $3, updated_at = now()
                        WHERE edge_id = $1
                        RETURNING *
                        """,
                        edge_id,
                        new_from,
                        new_to,
                    )
                    await reflect_edge(
                        conn,
                        edge_id=edge_id,
                        tenant=tenant,
                        relationship_type=updated["type"],
                        from_concept_id=str(updated["from_concept_id"]),
                        to_concept_id=str(updated["to_concept_id"]),
                        state=updated["state"],
                        confidence=float(updated["confidence"]),
                    )

                into_before = dict(into_row)
                merged_aliases = list(into_before["aliases"] or [])
                for source in sources:
                    source_data = dict(source)
                    merged_aliases.extend(source_data["aliases"] or [])
                    merged_aliases.append(source_data["name"])
                merged_aliases = sorted(
                    {
                        alias.strip()
                        for alias in merged_aliases
                        if alias and alias.strip() and alias.strip() != into_before["name"]
                    }
                )
                into_after_row = await conn.fetchrow(
                    """
                    UPDATE opencg.concept
                    SET aliases = $3, updated_at = now()
                    WHERE tenant = $1 AND concept_id = $2
                    RETURNING *
                    """,
                    tenant,
                    into_id,
                    merged_aliases,
                )
                into_after = dict(into_after_row)
                await reflect_concept(
                    conn,
                    concept_id=into_id,
                    tenant=tenant,
                    name=into_after["name"],
                    state=into_after["state"],
                )
                await _write_audit(
                    conn,
                    actor=actor,
                    tenant=tenant,
                    target_kind="concept",
                    target_id=into_id,
                    from_state=into_before["state"],
                    to_state=into_after["state"],
                    reason=reason or "concept merge target updated",
                    before=into_before,
                    after=into_after,
                )

                for source in sources:
                    before = dict(source)
                    source_id = str(before["concept_id"])
                    after_row = await conn.fetchrow(
                        """
                        UPDATE opencg.concept
                        SET state = 'tombstoned',
                            tombstoned_at = COALESCE(tombstoned_at, now()),
                            updated_at = now()
                        WHERE tenant = $1 AND concept_id = $2
                        RETURNING *
                        """,
                        tenant,
                        source_id,
                    )
                    after = dict(after_row)
                    await reflect_concept(
                        conn,
                        concept_id=source_id,
                        tenant=tenant,
                        name=after["name"],
                        state="tombstoned",
                    )
                    await _write_audit(
                        conn,
                        actor=actor,
                        tenant=tenant,
                        target_kind="concept",
                        target_id=source_id,
                        from_state=before["state"],
                        to_state="tombstoned",
                        reason=reason or f"merged into {into_id}",
                        before=before,
                        after=after,
                    )
                return into_after


def _validated_relation(name: str) -> str:
    if not _RELATION_RE.fullmatch(name):
        raise ValueError(f"invalid relationship type: {name!r}")
    return name


def _agtype_text(value: Any) -> str:
    text = str(value)
    try:
        decoded = json.loads(text)
        return str(decoded)
    except json.JSONDecodeError:
        return text.strip('"')


def _normalise_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _reachable_ids(
    *,
    concept_id: str,
    edges: list[dict[str, Any]],
    depth: int,
    limit: int,
) -> list[str]:
    if limit <= 1:
        return [concept_id]

    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        source = str(edge["from_concept_id"])
        target = str(edge["to_concept_id"])
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    ordered = [concept_id]
    seen = {concept_id}
    frontier = {concept_id}
    for _ in range(depth):
        next_frontier: set[str] = set()
        for current in sorted(frontier):
            for peer in sorted(adjacency.get(current, ())):
                if peer in seen:
                    continue
                seen.add(peer)
                ordered.append(peer)
                next_frontier.add(peer)
                if len(ordered) >= limit:
                    return ordered
        if not next_frontier:
            break
        frontier = next_frontier
    return ordered


async def _assert_active_vocab(conn: Any, name: str) -> None:
    active = await conn.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM opencg.relationship_vocab
          WHERE name = $1 AND deprecated_at IS NULL
        )
        """,
        name,
    )
    if not active:
        raise ValueError("vocab_deprecated_or_unknown")


async def _write_audit(
    conn: Any,
    *,
    actor: str,
    tenant: str,
    target_kind: str,
    target_id: str,
    from_state: str | None,
    to_state: str | None,
    reason: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    try:
        await _insert_graph_audit(
            conn,
            actor=actor,
            tenant=tenant,
            target_kind=target_kind,
            target_id=target_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            before=before,
            after=after,
        )
    except Exception:
        record_audit_write("graph", "error")
        raise
    record_audit_write("graph", "ok")


async def _insert_graph_audit(
    conn: Any,
    *,
    actor: str,
    tenant: str,
    target_kind: str,
    target_id: str,
    from_state: str | None,
    to_state: str | None,
    reason: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO opencg.graph_audit_log (
          actor, tenant, target_kind, target_id, from_state, to_state,
          reason, before, after
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
        """,
        actor,
        tenant,
        target_kind,
        target_id,
        from_state,
        to_state,
        reason,
        json.dumps(before, default=str) if before is not None else None,
        json.dumps(after, default=str) if after is not None else None,
    )
