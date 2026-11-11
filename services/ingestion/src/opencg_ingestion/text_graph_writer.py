"""Persists an LLM-extractor `ExtractionResult` into the same concept +
edge tables that `graph_writer.py` (code-side) uses.

Differences from the code writer:
- Concepts and edges land in `state = "candidate"` by default — the LLM
  output is non-deterministic, so reviewers should triage before edges
  enter traversal results. (Configurable per-call via `auto_confirm`.)
- The mapping pass is trivial: relation names are already in-vocabulary
  thanks to `filter_result` in the extractor.
- All writes use a single Postgres transaction; partial failure rolls back.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from typing import Any

from opencg_pipeline.graph.age import reflect_concept, reflect_edge
from opencg_pipeline.storage.catalog import CatalogStore
from opencg_shared import ExtractionResult

log = logging.getLogger(__name__)

_CONCEPT_NS = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000010")
_EDGE_NS = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000011")


def _normalize(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _concept_uuid(tenant: str, dedupe_key: str) -> str:
    return str(uuid.uuid5(_CONCEPT_NS, f"{tenant}:{dedupe_key}"))


def _edge_uuid(tenant: str, from_id: str, etype: str, to_id: str) -> str:
    return str(uuid.uuid5(_EDGE_NS, f"{tenant}:{from_id}:{etype}:{to_id}"))


async def write_text_graph(
    *,
    catalog: CatalogStore,
    tenant: str,
    chunk_entity_id: str,
    result: ExtractionResult,
    extractor_version: str,
) -> tuple[int, int]:
    """Persist the LLM-extracted concepts + edges. Returns (concepts, edges)."""
    if not result.concepts and not result.relations:
        return 0, 0

    pool = catalog._require_pool()
    concepts_written = 0
    edges_written = 0
    # Track which concept names we've inserted in this batch so subsequent
    # relation endpoint inserts can resolve without a SELECT round-trip.
    name_to_id: dict[str, str] = {}

    async with pool.acquire() as conn:
        async with conn.transaction():
            for c in result.concepts:
                dedupe = _normalize(c.name)
                if not dedupe:
                    continue
                concept_id = _concept_uuid(tenant, dedupe)
                stored_concept = await conn.fetchrow(
                    """
                    INSERT INTO opencg.concept (
                      concept_id, tenant, name, dedupe_key, description,
                      aliases, state, confidence, extractor_version,
                      source_entity_id
                    ) VALUES (
                      $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
                    )
                    ON CONFLICT (tenant, dedupe_key) DO UPDATE SET
                      description = COALESCE(EXCLUDED.description, opencg.concept.description),
                      aliases = COALESCE(
                        (SELECT array_agg(DISTINCT a)
                         FROM unnest(opencg.concept.aliases || EXCLUDED.aliases) AS a),
                        '{}'::text[]
                      ),
                      extractor_version = EXCLUDED.extractor_version,
                      updated_at = now()
                    RETURNING concept_id::text, state
                    """,
                    concept_id,
                    tenant,
                    c.name.strip(),
                    dedupe,
                    c.description,
                    list(c.aliases),
                    "candidate",
                    None,
                    extractor_version,
                    chunk_entity_id,
                )
                concept_id = str(stored_concept["concept_id"])
                name_to_id[dedupe] = concept_id
                await reflect_concept(
                    conn,
                    concept_id=concept_id,
                    tenant=tenant,
                    name=c.name.strip(),
                    state=str(stored_concept["state"]),
                )
                concepts_written += 1

            for r in result.relations:
                from_dedupe = _normalize(r.from_)
                to_dedupe = _normalize(r.to)
                if not from_dedupe or not to_dedupe:
                    continue
                # Resolve endpoints; insert on-the-fly concept rows for ones
                # the extractor mentioned only as relation endpoints.
                from_id = name_to_id.get(from_dedupe) or await _ensure_concept(
                    conn,
                    tenant=tenant,
                    name=r.from_,
                    dedupe=from_dedupe,
                    extractor_version=extractor_version,
                    chunk_entity_id=chunk_entity_id,
                )
                name_to_id.setdefault(from_dedupe, from_id)
                to_id = name_to_id.get(to_dedupe) or await _ensure_concept(
                    conn,
                    tenant=tenant,
                    name=r.to,
                    dedupe=to_dedupe,
                    extractor_version=extractor_version,
                    chunk_entity_id=chunk_entity_id,
                )
                name_to_id.setdefault(to_dedupe, to_id)
                edge_id = _edge_uuid(tenant, from_id, r.relation, to_id)
                stored_edge = await conn.fetchrow(
                    """
                    INSERT INTO opencg.relationship_edge (
                      edge_id, tenant, type, from_concept_id, to_concept_id,
                      state, confidence, extractor_version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (tenant, from_concept_id, type, to_concept_id) DO UPDATE SET
                      confidence = GREATEST(opencg.relationship_edge.confidence, EXCLUDED.confidence),
                      extractor_version = EXCLUDED.extractor_version,
                      updated_at = now()
                    RETURNING edge_id::text, state, confidence
                    """,
                    edge_id,
                    tenant,
                    r.relation,
                    from_id,
                    to_id,
                    "candidate",
                    float(r.confidence),
                    extractor_version,
                )
                edge_id = str(stored_edge["edge_id"])
                await reflect_edge(
                    conn,
                    edge_id=edge_id,
                    tenant=tenant,
                    relationship_type=r.relation,
                    from_concept_id=from_id,
                    to_concept_id=to_id,
                    state=str(stored_edge["state"]),
                    confidence=float(stored_edge["confidence"]),
                )
                await conn.execute(
                    """
                    INSERT INTO opencg.relationship_evidence (
                      edge_id, entity_id, span, extractor_version, confidence
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    edge_id,
                    chunk_entity_id,
                    r.evidence_span,
                    extractor_version,
                    float(r.confidence),
                )
                edges_written += 1
    return concepts_written, edges_written


async def _ensure_concept(
    conn: Any,
    *,
    tenant: str,
    name: str,
    dedupe: str,
    extractor_version: str,
    chunk_entity_id: str,
) -> str:
    concept_id = _concept_uuid(tenant, dedupe)
    stored_concept = await conn.fetchrow(
        """
        WITH inserted AS (
          INSERT INTO opencg.concept (
            concept_id, tenant, name, dedupe_key,
            state, confidence, extractor_version, source_entity_id
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          ON CONFLICT (tenant, dedupe_key) DO NOTHING
          RETURNING concept_id, state
        )
        SELECT concept_id::text, state FROM inserted
        UNION ALL
        SELECT concept_id::text, state
        FROM opencg.concept
        WHERE tenant = $2 AND dedupe_key = $4
        LIMIT 1
        """,
        concept_id,
        tenant,
        name.strip(),
        dedupe,
        "candidate",
        None,
        extractor_version,
        chunk_entity_id,
    )
    concept_id = str(stored_concept["concept_id"])
    await reflect_concept(
        conn,
        concept_id=concept_id,
        tenant=tenant,
        name=name.strip(),
        state=str(stored_concept["state"]),
    )
    return concept_id


# --- Vocabulary loader -----------------------------------------------------


async def load_vocabulary(catalog: CatalogStore, tenant: str) -> list[str]:
    """Fetch active (non-deprecated) vocabulary names.

    Tenant is unused at the schema level (vocab is global), but accepted
    for symmetry with other helpers in case we tenant-scope it later.
    """
    pool = catalog._require_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name FROM opencg.relationship_vocab WHERE deprecated_at IS NULL ORDER BY name"
        )
    return [r["name"] for r in rows]
