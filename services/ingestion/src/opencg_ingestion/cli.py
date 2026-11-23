"""opencg-ingest CLI."""

from __future__ import annotations

import logging
from datetime import datetime

import click
from opencg_shared import load_config
from opencg_shared.authz import is_valid_classification

from opencg_ingestion.pipeline_runner import run_sync
from opencg_ingestion.reextract import reextract_sync


@click.group()
def main() -> None:
    """openCG ingestion CLI."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@main.command()
@click.argument("repo_url")
@click.option(
    "--max-documents",
    type=click.IntRange(min=1),
    default=None,
    help="Stop after this many repository documents.",
)
@click.option(
    "--max-chunks",
    type=click.IntRange(min=1),
    default=None,
    help="Stop after this many chunks across all documents.",
)
@click.option(
    "--classification",
    default="internal",
    show_default=True,
    help="Classification for every entity the run creates: public, internal or "
    "confidential:<domain>.",
)
def git(
    repo_url: str, max_documents: int | None, max_chunks: int | None, classification: str
) -> None:
    """Ingest a public git repository (clone, walk, embed)."""
    if not is_valid_classification(classification):
        raise click.BadParameter(
            "must be public, internal or confidential:<domain> "
            "(domain: lowercase letters, digits and hyphens)",
            param_hint="--classification",
        )
    cfg = load_config()
    summary = run_sync(
        repo_url,
        cfg,
        max_documents=max_documents,
        max_chunks=max_chunks,
        classification=classification,
    )
    limits = []
    if summary.document_limit is not None:
        limits.append(f"max_documents={summary.document_limit}")
    if summary.chunk_limit is not None:
        limits.append(f"max_chunks={summary.chunk_limit}")
    truncation = []
    if summary.documents_truncated:
        truncation.append("documents")
    if summary.chunks_truncated:
        truncation.append("chunks")
    suffix = f" limits={','.join(limits)}" if limits else ""
    suffix += f" truncated={','.join(truncation)}" if truncation else " truncated=none"
    click.echo(
        f"Ingested {summary.parents} files / {summary.chunks} chunks from {repo_url}{suffix}"
    )


@main.command("re-extract")
@click.option("--source", default=None, help="Only re-extract chunks from this source.")
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    default=None,
    help="Only re-extract chunks updated on or after this timestamp.",
)
def re_extract(source: str | None, since: datetime | None) -> None:
    """Re-run graph extraction over existing text chunks."""
    summary = reextract_sync(load_config(), source=source, since=since)
    click.echo(
        "Re-extract complete: "
        f"succeeded={summary.succeeded} failed={summary.failed} skipped={summary.skipped}"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
