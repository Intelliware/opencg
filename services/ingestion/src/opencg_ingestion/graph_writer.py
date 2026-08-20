"""Persists a graphifyy `{nodes, edges}` result into our concept + edge
tables.

graphifyy's relation names (`calls`, `imports`, `imports_from`, `contains`,
`method`) are richer than the three new vocabulary entries this change
adds. The writer maps them to a smaller in-vocab set so every edge type
satisfies the FK on `relationship_vocab`:

    calls          → calls               (new vocab)
    imports        → imports             (new vocab)
    imports_from   → imports             (mapped onto new vocab)
    contains       → defined_in          (existing vocab)
    method         → defined_in          (existing vocab)
    uses           → uses                (new vocab)

Anything we cannot map is dropped with a log.

Auto-confirm policy (D2 in design.md):
    EXTRACTED  → state="confirmed",  confidence=1.0
    INFERRED   → state="confirmed",  confidence=0.85
    AMBIGUOUS  → state="candidate",  confidence=0.5
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from typing import Any

from opencg_pipeline.graph.age import reflect_concept, reflect_edge
from opencg_pipeline.storage.catalog import CatalogStore

from opencg_ingestion.graphifyy_version import graphifyy_extractor_version

log = logging.getLogger(__name__)


_CONCEPT_NS = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000010")
_EDGE_NS = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000011")


_RELATION_MAP: dict[str, str] = {
    "calls": "calls",
    "imports": "imports",
    "imports_from": "imports",
    "contains": "defined_in",
    "method": "defined_in",
    "uses": "uses",
}


_CONFIDENCE_MAP: dict[str, tuple[str, float]] = {
    "EXTRACTED": ("confirmed", 1.0),
    "INFERRED":  ("confirmed", 0.85),
    "AMBIGUOUS": ("candidate", 0.5),
}


def _normalize(name: str) -> str:
    """Dedupe-key normalisation: lowercase + Unicode-fold + squeeze whitespace."""
    s = unicodedata.normalize("NFKC", name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _concept_uuid(tenant: str, dedupe_key: str) -> str:
    return str(uuid.uuid5(_CONCEPT_NS, f"{tenant}:{dedupe_key}"))


def _edge_uuid(tenant: str, from_id: str, etype: str, to_id: str) -> str:
    return str(uuid.uuid5(_EDGE_NS, f"{tenant}:{from_id}:{etype}:{to_id}"))


def _kind_from_label(label: str | None) -> str | None:
    if not label:
        return None
    if label.endswith("()"):
        return "method" if label.startswith(".") else "function"
    return "class"


async def write_code_graph(
    *,
    catalog: CatalogStore,
    tenant: str,
    file_entity_id: str,
    graphify_result: dict[str, Any],
) -> tuple[int, int]:
    """Persist nodes + edges into Postgres. Returns (concepts_written, edges_written).

    All writes happen in a single transaction obtained from the catalog's
    pool, so a partial failure rolls back cleanly.
    """
    nodes = [
        n
        for n in graphify_result.get("nodes", [])
        if n.get("_origin") == "ast" and n.get("file_type") == "code"
    ]
    edges = list(graphify_result.get("edges", []))

    # Build a graphify-id → (concept_uuid, label) map so edges can resolve
    # endpoints without round-trips.
    id_to_concept: dict[str, tuple[str, str]] = {}

    pool = catalog._require_pool()  # noqa: SLF001 — share the lifespan pool
    concepts_written = 0
    edges_written = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for node in nodes:
                label = node.get("label") or node.get("id") or ""
                if not label:
                    continue
                dedupe = _normalize(label)
                if not dedupe:
                    continue
                concept_id = _concept_uuid(tenant, dedupe)
                id_to_concept[node["id"]] = (concept_id, label)
                kind = _kind_from_label(label)
                await conn.execute(
                    """
                    INSERT INTO opencg.concept (
                      concept_id, tenant, name, dedupe_key, description,
                      state, confidence, extractor_version,
                      symbol_id, symbol_kind, source_entity_id
                    ) VALUES (
                      $1, $2, $3, $4, $5,
                      $6, $7, $8,
                      $9, $10, $11
                    )
                    ON CONFLICT (tenant, dedupe_key) DO UPDATE SET
                      symbol_id = COALESCE(EXCLUDED.symbol_id, opencg.concept.symbol_id),
                      symbol_kind = COALESCE(EXCLUDED.symbol_kind, opencg.concept.symbol_kind),
                      extractor_version = EXCLUDED.extractor_version,
                      updated_at = now()
                    """,
                    concept_id,
                    tenant,
                    label,
                    dedupe,
                    None,
                    "confirmed",
                    1.0,
                    graphifyy_extractor_version(),
                    node["id"],
                    kind,
                    file_entity_id,
                )
                await reflect_concept(
                    conn,
                    concept_id=concept_id,
                    tenant=tenant,
                    name=label,
                    state="confirmed",
                )
                concepts_written += 1

            for edge in edges:
                relation = edge.get("relation", "")
                mapped = _RELATION_MAP.get(relation)
                if mapped is None:
                    # Unknown relation type — skip.
                    log.debug("unknown graphify relation %r — skipping", relation)
                    continue
                from_node = id_to_concept.get(edge.get("source"))
                # graphify can emit edges whose target is an external module
                # name (e.g., `imports os`). Create a concept on the fly for
                # that target if it isn't in our node lookup.
                to_node = id_to_concept.get(edge.get("target"))
                if to_node is None and edge.get("target"):
                    target_label = edge["target"]
                    target_dedupe = _normalize(target_label)
                    target_concept_id = _concept_uuid(tenant, target_dedupe)
                    await conn.execute(
                        """
                        INSERT INTO opencg.concept (
                          concept_id, tenant, name, dedupe_key,
                          state, confidence, extractor_version,
                          source_entity_id
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        ON CONFLICT (tenant, dedupe_key) DO NOTHING
                        """,
                        target_concept_id,
                        tenant,
                        target_label,
                        target_dedupe,
                        "confirmed",
                        1.0,
                        graphifyy_extractor_version(),
                        file_entity_id,
                    )
                    await reflect_concept(
                        conn,
                        concept_id=target_concept_id,
                        tenant=tenant,
                        name=target_label,
                        state="confirmed",
                    )
                    to_node = (target_concept_id, target_label)
                    id_to_concept[edge["target"]] = to_node
                    concepts_written += 1
                if from_node is None or to_node is None:
                    continue
                conf_label = edge.get("confidence", "EXTRACTED")
                state, conf_value = _CONFIDENCE_MAP.get(
                    conf_label, ("confirmed", 1.0)
                )
                edge_id = _edge_uuid(tenant, from_node[0], mapped, to_node[0])
                await conn.execute(
                    """
                    INSERT INTO opencg.relationship_edge (
                      edge_id, tenant, type, from_concept_id, to_concept_id,
                      state, confidence, extractor_version
                    ) VALUES (
                      $1, $2, $3, $4, $5, $6, $7, $8
                    )
                    ON CONFLICT (tenant, from_concept_id, type, to_concept_id) DO UPDATE SET
                      state = EXCLUDED.state,
                      confidence = GREATEST(opencg.relationship_edge.confidence, EXCLUDED.confidence),
                      extractor_version = EXCLUDED.extractor_version,
                      updated_at = now()
                    """,
                    edge_id,
                    tenant,
                    mapped,
                    from_node[0],
                    to_node[0],
                    state,
                    conf_value,
                    graphifyy_extractor_version(),
                )
                await reflect_edge(
                    conn,
                    edge_id=edge_id,
                    tenant=tenant,
                    relationship_type=mapped,
                    from_concept_id=from_node[0],
                    to_concept_id=to_node[0],
                    state=state,
                    confidence=conf_value,
                )
                await conn.execute(
                    """
                    INSERT INTO opencg.relationship_evidence (
                      edge_id, entity_id, span, extractor_version, confidence
                    ) VALUES ($1, $2, $3, $4, $5)
                    """,
                    edge_id,
                    file_entity_id,
                    edge.get("source_location"),
                    graphifyy_extractor_version(),
                    conf_value,
                )
                edges_written += 1

    return concepts_written, edges_written
