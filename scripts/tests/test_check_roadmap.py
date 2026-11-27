"""Unit tests for scripts/check-roadmap.py (run by `make test-scripts`)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("check_roadmap", SCRIPTS / "check-roadmap.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up while it loads
    spec.loader.exec_module(module)
    return module


cr = _load()


def item(
    id_: str,
    status: str = "ready",
    size: str = "S",
    caps: str = "ingestion",
    depends: str = "none",
    extra: str = "",
    body: str = "**Problem:** p.\n\n**Scope:** s.",
) -> str:
    return (
        f"### {id_}\n\n- **Status:** {status}\n- **Size:** {size}\n- **Capabilities:** {caps}\n"
        f"- **Depends on:** {depends}\n- **Source:** test\n{extra}\n{body}\n\n"
    )


@pytest.fixture
def repo(tmp_path: Path):
    (tmp_path / "openspec" / "specs" / "ingestion").mkdir(parents=True)
    (tmp_path / "openspec" / "changes" / "archive").mkdir(parents=True)

    def build(roadmap: str, in_flight=(), archived=()):
        (tmp_path / "ROADMAP.md").write_text("# Roadmap\n\n## How\n\ntext\n\n" + roadmap)
        for name in in_flight:
            (tmp_path / "openspec" / "changes" / name).mkdir()
        for name in archived:
            (tmp_path / "openspec" / "changes" / "archive" / f"2026-11-27-{name}").mkdir()
        return cr.check(tmp_path)

    return build


def test_consistent_roadmap_passes(repo):
    roadmap = (
        "## Now\n\n"
        + item("add-a", status="in-progress")
        + "## Later\n\n"
        + item("add-b", depends="add-a, done-c")
    )
    assert repo(roadmap, in_flight=["add-a"], archived=["done-c"]) == []


def test_missing_roadmap(tmp_path):
    assert cr.check(tmp_path) == ["ROADMAP.md is missing"]


@pytest.mark.parametrize(
    ("roadmap", "expected"),
    [
        (item("add-a"), "put the item under"),
        ("## Now\n\n" + item("Add_A"), "kebab-case"),
        ("## Now\n\n" + item("add-a") + item("add-a"), "duplicate ID"),
        ("## Now\n\n" + item("add-a", status="done"), "Status must be one of"),
        ("## Now\n\n" + item("add-a", size="XL"), "Size must be S, M or L"),
        ("## Now\n\n" + item("add-a", caps="nope"), "capability 'nope'"),
        ("## Now\n\n" + item("add-a", depends="ghost"), "depends on 'ghost'"),
        ("## Now\n\n" + item("add-a", extra="- **Priority:** high"), "unknown field 'Priority'"),
        ("## Now\n\n" + item("add-a", body="**Scope:** s."), "add a **Problem:**"),
        ("## Now\n\n### add-a\n\n**Problem:** p.\n\n**Scope:** s.\n", "add '- **Status:** …'"),
    ],
)
def test_malformed_items_fail(repo, roadmap, expected):
    problems = repo(roadmap)
    assert any(expected in p for p in problems), problems


def test_new_capability_is_allowed(repo):
    assert repo("## Now\n\n" + item("add-a", caps="new: shiny, ingestion")) == []


def test_capability_from_in_flight_change_is_allowed(repo, tmp_path):
    (tmp_path / "openspec" / "changes" / "add-a" / "specs" / "identity-access").mkdir(parents=True)
    roadmap = (
        "## Now\n\n" + item("add-a", status="proposed") + item("add-b", caps="identity-access")
    )
    assert repo(roadmap) == []


@pytest.mark.parametrize("status", ["proposed", "in-progress"])
def test_started_status_without_change_fails(repo, status):
    problems = repo("## Now\n\n" + item("add-a", status=status))
    assert any("openspec/changes/add-a/ doesn't exist" in p for p in problems), problems


def test_ready_item_with_change_fails(repo):
    problems = repo("## Now\n\n" + item("add-a"), in_flight=["add-a"])
    assert any("set Status to proposed" in p for p in problems), problems


def test_archived_item_still_listed_fails(repo):
    problems = repo("## Now\n\n" + item("add-a", status="in-progress"), archived=["add-a"])
    assert any("archived (shipped); delete the item" in p for p in problems), problems


def test_in_flight_change_without_item_fails(repo):
    problems = repo("## Now\n\n" + item("add-a"), in_flight=["add-z"])
    assert any("openspec/changes/add-z/ has no roadmap item" in p for p in problems), problems


def test_repository_roadmap_is_consistent():
    assert cr.check(SCRIPTS.parent) == []
