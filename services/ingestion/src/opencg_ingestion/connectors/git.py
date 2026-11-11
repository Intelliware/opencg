"""Git connector — clones a repo into a temp dir, walks files via graphifyy,
emits documents.

The discovery loop delegates to `graphify.collect_files`, which knows 80+
file extensions across 28 tree-sitter-supported languages and honours a
`.graphifyignore` file in the cloned repo. Our responsibility is the clone,
the stable-id derivation, and the GitDocument shape — those are unchanged.

See openspec/changes/adopt-graphifyy/specs/ingestion/spec.md for the contract.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from graphify import collect_files

log = logging.getLogger(__name__)

# Non-code text extensions we ingest with the paragraph chunker. Code
# extensions are detected by graphifyy's dispatch table at pipeline-runner
# time; this set is the fallback / additional surface for prose-y files
# graphifyy doesn't (and shouldn't) parse.
TEXT_EXTS = {
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".ini",
    ".html",
    ".css",
    ".scss",
    ".sass",
}

MAX_FILE_BYTES = 1_000_000  # 1 MB cap per file


@dataclass
class GitDocument:
    entity_id: str
    title: str
    body: str
    source: str
    source_uri: str
    source_revision: str
    content_hash: str
    metadata: dict


def _stable_id(tenant: str, source_uri: str) -> str:
    """Deterministic UUID for (tenant, source_uri). Re-ingest keeps the same id."""
    ns = uuid.UUID("6e3a4d1e-0000-0000-0000-000000000001")
    return str(uuid.uuid5(ns, f"{tenant}:{source_uri}"))


def _content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def clone(repo_url: str, dest: Path) -> str:
    """Clone repo, return the commit SHA."""
    subprocess.run(
        # `--` ends option parsing so a URL can never be read as a git option.
        ["git", "clone", "--depth", "1", "--", repo_url, str(dest)],
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return sha


def _discover_files(repo_path: Path) -> list[Path]:
    """File discovery via graphifyy + our text-ext fallback.

    `collect_files` covers code (Python, TS, Go, Rust, Kotlin, Swift, Elixir,
    Lua, Zig, Verilog, ...) including ~80 extensions we don't enumerate. The
    `TEXT_EXTS` fallback catches Markdown, plain text, YAML, JSON, etc. that
    graphifyy doesn't parse but we still want to embed.
    """
    code_files = collect_files(repo_path)
    text_files = [p for p in repo_path.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTS]
    # Dedupe — `collect_files` may include some files (e.g. .json) that also
    # appear in TEXT_EXTS. Code path wins; the runner dispatches by extension.
    seen = {p.resolve() for p in code_files}
    merged = list(code_files)
    for p in text_files:
        if p.resolve() not in seen:
            merged.append(p)
    return merged


def walk_repo(
    *, tenant: str, repo_url: str, repo_path: Path, revision: str
) -> Iterator[GitDocument]:
    """Walk the cloned repo via graphifyy + text fallback, yield GitDocuments.

    Per-file errors (unreadable, non-utf8, oversize) skip the offending file
    with a structured log and continue the iteration — the ingest must not
    fail on a single bad file.
    """
    repo_name = repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    try:
        paths = _discover_files(repo_path)
    except Exception as exc:
        log.error("file discovery failed for %s: %s", repo_path, exc)
        return

    for path in paths:
        try:
            if not path.is_file():
                continue
            data = path.read_bytes()
        except OSError as exc:
            log.warning("skip %s: %s", path, exc)
            continue
        if len(data) > MAX_FILE_BYTES:
            log.info("skip large file %s (%d bytes)", path, len(data))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            log.info("skip non-utf8 %s", path)
            continue
        rel = path.relative_to(repo_path).as_posix()
        source_uri = f"git://{repo_name}/{rel}"
        yield GitDocument(
            entity_id=_stable_id(tenant, source_uri),
            title=rel,
            body=text,
            source="git",
            source_uri=source_uri,
            source_revision=revision,
            content_hash=_content_hash(data),
            metadata={"path": rel, "ext": path.suffix.lower(), "size": len(data)},
        )


def ingest_repo(repo_url: str, tenant: str) -> Iterator[GitDocument]:
    """High-level: clone into a temp dir and walk it."""
    with tempfile.TemporaryDirectory(prefix="opencg-git-") as tmp:
        dest = Path(tmp)
        sha = clone(repo_url, dest)
        log.info("cloned %s @ %s", repo_url, sha[:7])
        yield from walk_repo(tenant=tenant, repo_url=repo_url, repo_path=dest, revision=sha)
