from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from opencg_ingestion.connectors.git import (
    GitDocument,
    _stable_id,
    walk_repo,
)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Set up a tiny git repo on disk with a couple of text files and skip dirs."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# hi\n\nworld\n")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("def main():\n    return 42\n")
    # Skip-listed dir with junk we expect not to ingest.
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "junk.js").write_text("// noise")
    # Binary-ish file (skip by extension).
    (repo / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 100)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"],
        check=True,
        env={
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/usr/local/bin:/opt/homebrew/bin",
        },
    )
    return repo


def test_walk_repo_yields_text_files_only(fake_repo: Path):
    docs = list(
        walk_repo(
            tenant="t", repo_url="https://example.com/x.git", repo_path=fake_repo, revision="abc"
        )
    )
    paths = sorted(d.metadata["path"] for d in docs)
    assert "README.md" in paths
    assert "src/main.py" in paths
    # node_modules excluded, image.png excluded
    assert all("node_modules" not in p for p in paths)
    assert "image.png" not in paths


def test_stable_id_is_deterministic():
    a = _stable_id("t", "git://x/file.md")
    b = _stable_id("t", "git://x/file.md")
    assert a == b
    c = _stable_id("t", "git://x/other.md")
    assert a != c


def test_stable_id_tenant_isolation():
    assert _stable_id("t1", "git://x/file.md") != _stable_id("t2", "git://x/file.md")


def test_walk_repo_document_shape(fake_repo: Path):
    docs = list(
        walk_repo(
            tenant="t", repo_url="https://example.com/x.git", repo_path=fake_repo, revision="abc"
        )
    )
    readme = next(d for d in docs if d.metadata["path"] == "README.md")
    assert isinstance(readme, GitDocument)
    assert readme.source == "git"
    assert readme.source_revision == "abc"
    assert readme.source_uri.startswith("git://x/")
    assert readme.title == "README.md"
    assert readme.content_hash  # populated
    assert "world" in readme.body


def test_walk_repo_yields_languages_beyond_old_allowlist(tmp_path: Path):
    """Our hand-rolled TEXT_EXTS didn't list .kt or .swift; graphifyy does."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.kt").write_text("class App { fun main() {} }\n")
    (repo / "View.swift").write_text("struct View {}\n")
    (repo / "README.md").write_text("# hi\n")

    docs = list(
        walk_repo(
            tenant="t",
            repo_url="https://example.com/x.git",
            repo_path=repo,
            revision="abc",
        )
    )
    paths = sorted(d.metadata["path"] for d in docs)
    assert "App.kt" in paths
    assert "View.swift" in paths
    assert "README.md" in paths


def test_walk_repo_honours_graphifyignore(tmp_path: Path):
    """Files matched by .graphifyignore must not be yielded."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "vendor").mkdir()
    (repo / "vendor" / "lib.py").write_text("def vendored(): pass\n")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("def app(): pass\n")
    (repo / ".graphifyignore").write_text("vendor/\n")

    docs = list(
        walk_repo(
            tenant="t",
            repo_url="https://example.com/x.git",
            repo_path=repo,
            revision="abc",
        )
    )
    paths = [d.metadata["path"] for d in docs]
    assert "src/app.py" in paths
    assert all("vendor" not in p for p in paths)
