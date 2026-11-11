"""Re-run text graph extraction over existing catalog chunks."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from opencg_pipeline.graph.extract import extract_for_chunk
from opencg_pipeline.providers import OllamaChat
from opencg_pipeline.storage.catalog import CatalogStore
from opencg_shared import openCGConfig

from opencg_ingestion.text_graph_writer import load_vocabulary, write_text_graph

log = logging.getLogger(__name__)


@dataclass
class ReextractSummary:
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0


def current_extractor_version(model: str) -> str:
    return f"text-extractor/v1/{model}"


def version_is_current_or_newer(existing: str | None, current: str) -> bool:
    if not existing:
        return False
    pattern = re.compile(r"^text-extractor/v(\d+)(?:/|$)")
    existing_match = pattern.match(existing)
    current_match = pattern.match(current)
    if existing_match and current_match:
        return int(existing_match.group(1)) >= int(current_match.group(1))
    return existing == current


async def reextract_chunks(
    cfg: openCGConfig,
    *,
    source: str | None = None,
    since: datetime | None = None,
) -> ReextractSummary:
    chat_cfg = cfg.providers.chat
    if not cfg.providers.extraction.enabled or chat_cfg is None:
        return ReextractSummary()
    catalog = CatalogStore(cfg.postgres.url)
    chat = OllamaChat(
        base_url=chat_cfg.base_url,
        model=chat_cfg.model,
        api_key=chat_cfg.api_key,
    )
    version = current_extractor_version(chat_cfg.model)
    await catalog.connect()
    try:
        vocabulary = await load_vocabulary(catalog, cfg.tenant)
        rows = await _list_chunks(
            catalog,
            tenant=cfg.tenant,
            source=source,
            since=since,
        )
        summary = ReextractSummary()
        for row in rows:
            if version_is_current_or_newer(row.get("extractor_version"), version):
                summary.skipped += 1
                continue
            try:
                result, _ = await extract_for_chunk(
                    chunk_text=row["body"],
                    chunk_entity_id=row["entity_id"],
                    vocabulary=vocabulary,
                    chat=chat,
                    tenant=cfg.tenant,
                    min_confidence=cfg.providers.extraction.min_confidence,
                    timeout_seconds=cfg.providers.extraction.timeout_seconds,
                )
                await write_text_graph(
                    catalog=catalog,
                    tenant=cfg.tenant,
                    chunk_entity_id=row["entity_id"],
                    result=result,
                    extractor_version=version,
                )
                summary.succeeded += 1
            except Exception as exc:
                summary.failed += 1
                log.warning("re-extract failed for chunk %s: %s", row["entity_id"], exc)
        return summary
    finally:
        await chat.close()
        await catalog.close()


def reextract_sync(
    cfg: openCGConfig,
    *,
    source: str | None = None,
    since: datetime | None = None,
) -> ReextractSummary:
    return asyncio.run(reextract_chunks(cfg, source=source, since=since))


async def _list_chunks(
    catalog: CatalogStore,
    *,
    tenant: str,
    source: str | None,
    since: datetime | None,
) -> list[dict]:
    clauses = [
        "entity.tenant = $1",
        "entity.parent_entity_id IS NOT NULL",
        "entity.tombstoned_at IS NULL",
    ]
    params: list[object] = [tenant]
    if source:
        params.append(source)
        clauses.append(f"entity.source = ${len(params)}")
    if since:
        params.append(since)
        clauses.append(f"entity.updated_at >= ${len(params)}")
    async with catalog._require_pool().acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT entity.entity_id::text, entity.body,
                   latest.extractor_version
            FROM opencg.entity entity
            LEFT JOIN LATERAL (
              SELECT evidence.extractor_version
              FROM opencg.relationship_evidence evidence
              WHERE evidence.entity_id = entity.entity_id
              ORDER BY evidence.created_at DESC, evidence.evidence_id DESC
              LIMIT 1
            ) latest ON TRUE
            WHERE {' AND '.join(clauses)}
            ORDER BY entity.updated_at, entity.entity_id
            """,
            *params,
        )
    return [dict(row) for row in rows]
