"""Tests for the OpenSpec parser.

Uses purpose-built fixture trees rather than the real `openspec/` directory so
the assertions stay stable as the project's own history grows. One test at the
end does run against the real tree, but only asserts invariants that must hold
for any valid repository state.
"""

from __future__ import annotations

from pathlib import Path

import openspec_reader as osr

REPO_ROOT = Path(__file__).resolve().parents[3]

PROPOSAL = """\
## Why

First paragraph of the rationale.
It wraps onto a second line.

A second paragraph that must not be captured.

## What Changes

- **A bold thing** with `code` in it.
- A second bullet
  that continues on the next line.

## Capabilities

### New Capabilities

- `brand-new`: this one is created here.

### Modified Capabilities

- `existing-one`: reshaped.
- `another-one`: also reshaped.
  - a nested bullet that must not register as a capability

## Impact

- New table: `thing`.
- Touches two services.

## Why this is one change

Trailing sections must not confuse the section splitter.
"""

TASKS = """\
## 1. Phase one

- [x] 1.1 Done
- [x] 1.2 Also done
- [ ] 1.3 Not done

## 2. Phase two

- [ ] 2.1 Open
"""

SPEC_DELTA = """\
## ADDED Requirements

### Requirement: A brand new rule

The system SHALL do the thing.

#### Scenario: It does the thing

- **WHEN** asked
- **THEN** it does it

#### Scenario: It refuses nonsense

- **WHEN** given nonsense
- **THEN** it fails loudly

## MODIFIED Requirements

### Requirement: An older rule

Now says something else.

#### Scenario: Still works

- **WHEN** exercised
- **THEN** it passes
"""


def _write_change(directory: Path, *, proposal=PROPOSAL, tasks=TASKS, specs=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "proposal.md").write_text(proposal, encoding="utf-8")
    (directory / "tasks.md").write_text(tasks, encoding="utf-8")
    for capability, body in (specs or {}).items():
        spec_dir = directory / "specs" / capability
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(body, encoding="utf-8")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "openspec"
    _write_change(
        root / "changes" / "archive" / "2026-01-15-shipped-thing",
        specs={"existing-one": SPEC_DELTA},
    )
    _write_change(root / "changes" / "in-flight-thing")
    _write_change(
        root / "changes" / "untouched-thing",
        tasks="## 1. Phase\n\n- [ ] 1.1 Nothing done\n",
    )
    baseline = root / "specs" / "existing-one"
    baseline.mkdir(parents=True, exist_ok=True)
    (baseline / "spec.md").write_text(SPEC_DELTA, encoding="utf-8")
    return root


# ---------------------------------------------------------------- section parsing


def test_split_sections_ignores_trailing_sections():
    sections = osr.split_sections(PROPOSAL)
    assert set(sections) == {
        "Why",
        "What Changes",
        "Capabilities",
        "Impact",
        "Why this is one change",
    }


def test_first_paragraph_joins_wrapped_lines_and_stops():
    assert osr.first_paragraph(osr.split_sections(PROPOSAL)["Why"]) == (
        "First paragraph of the rationale. It wraps onto a second line."
    )


def test_top_level_bullets_fold_continuations():
    bullets = osr.top_level_bullets(osr.split_sections(PROPOSAL)["What Changes"])
    assert bullets == [
        "**A bold thing** with `code` in it.",
        "A second bullet that continues on the next line.",
    ]


def test_capability_tags_split_new_from_modified():
    section = osr.split_sections(PROPOSAL)["Capabilities"]
    assert osr._capability_tags(section, "New Capabilities") == ["brand-new"]
    assert osr._capability_tags(section, "Modified Capabilities") == ["existing-one", "another-one"]


def test_capability_tags_ignore_nested_bullets():
    section = osr.split_sections(PROPOSAL)["Capabilities"]
    tags = osr._capability_tags(section, "Modified Capabilities")
    assert "a" not in tags and len(tags) == 2


def test_capability_tags_tolerate_a_none_placeholder():
    section = "### New Capabilities\n\nNone — nothing new here.\n\n### Modified Capabilities\n\n- `x`: y\n"
    assert osr._capability_tags(section, "New Capabilities") == []
    assert osr._capability_tags(section, "Modified Capabilities") == ["x"]


def test_capability_tags_missing_subsection_is_empty():
    assert osr._capability_tags("### Modified Capabilities\n\n- `a`: b\n", "New Capabilities") == []


# ---------------------------------------------------------------- tasks


def test_count_tasks_counts_done_and_total():
    assert osr.count_tasks(TASKS) == (2, 4)


def test_count_tasks_accepts_capital_x_and_indentation():
    assert osr.count_tasks("- [X] a\n  - [x] b\n    - [ ] c\n") == (2, 3)


def test_count_tasks_on_empty_input():
    assert osr.count_tasks("") == (0, 0)


# ---------------------------------------------------------------- spec deltas


def test_parse_spec_delta_tracks_operation_and_scenarios():
    deltas = osr.parse_spec_delta("existing-one", SPEC_DELTA)
    assert [(d.operation, d.requirement, len(d.scenarios)) for d in deltas] == [
        ("ADDED", "A brand new rule", 2),
        ("MODIFIED", "An older rule", 1),
    ]
    assert all(d.capability == "existing-one" for d in deltas)


def test_parse_spec_delta_defaults_to_modified_without_a_heading():
    deltas = osr.parse_spec_delta("c", "### Requirement: Bare\n\n#### Scenario: One\n")
    assert len(deltas) == 1
    assert deltas[0].operation == "MODIFIED"


def test_parse_spec_delta_on_empty_input():
    assert osr.parse_spec_delta("c", "") == []


# ---------------------------------------------------------------- whole tree


def test_read_changes_classifies_status_and_dates(tmp_path):
    changes = {c.name: c for c in osr.read_changes(_fixture_root(tmp_path))}

    assert changes["shipped-thing"].archived is True
    assert changes["shipped-thing"].date == "2026-01-15"
    assert changes["shipped-thing"].status == "shipped"

    assert changes["in-flight-thing"].archived is False
    assert changes["in-flight-thing"].date is None
    assert changes["in-flight-thing"].status == "in-flight"

    assert changes["untouched-thing"].status == "not-started"


def test_read_changes_sorts_active_ahead_of_archived(tmp_path):
    names = [c.name for c in osr.read_changes(_fixture_root(tmp_path))]
    assert names.index("in-flight-thing") < names.index("shipped-thing")


def test_read_changes_collects_deltas_from_change_specs(tmp_path):
    changes = {c.name: c for c in osr.read_changes(_fixture_root(tmp_path))}
    deltas = changes["shipped-thing"].deltas
    assert len(deltas) == 2
    assert {d.capability for d in deltas} == {"existing-one"}


def test_change_capabilities_dedupe_and_preserve_order(tmp_path):
    change = osr.read_changes(_fixture_root(tmp_path))[0]
    assert change.capabilities == ["brand-new", "existing-one", "another-one"]


def test_read_capabilities_reads_the_baseline(tmp_path):
    caps = osr.read_capabilities(_fixture_root(tmp_path))
    assert [c.name for c in caps] == ["existing-one"]
    assert caps[0].requirements == ["A brand new rule", "An older rule"]
    assert caps[0].scenario_count == 3


def test_read_all_is_json_ready_and_lists_every_tag(tmp_path):
    payload = osr.read_all(_fixture_root(tmp_path))
    assert payload["all_capability_tags"] == ["another-one", "brand-new", "existing-one"]
    assert isinstance(payload["changes"][0], dict)
    assert isinstance(payload["changes"][0]["deltas"], list)


def test_missing_openspec_tree_yields_nothing(tmp_path):
    payload = osr.read_all(tmp_path / "nope")
    assert payload["changes"] == []
    assert payload["capabilities"] == []


def test_change_with_no_proposal_does_not_explode(tmp_path):
    root = tmp_path / "openspec"
    (root / "changes" / "bare").mkdir(parents=True)
    changes = osr.read_changes(root)
    assert len(changes) == 1
    assert changes[0].why == ""
    assert changes[0].tasks_total == 0


# ---------------------------------------------------------------- real repository


def test_real_openspec_tree_parses_with_sane_invariants():
    """Guards against a real proposal drifting into a shape the parser mishandles."""
    payload = osr.read_all(REPO_ROOT / "openspec")

    assert payload["changes"], "expected at least one change in openspec/"
    for change in payload["changes"]:
        assert change["name"]
        assert change["status"] in {"shipped", "in-flight", "not-started"}
        assert change["tasks_done"] <= change["tasks_total"]
        # Every archived change must carry a date; the dir prefix supplies it.
        if change["archived"]:
            assert change["date"], f"{change['name']} is archived but has no date"
        # A capability tag is a slug, never prose.
        for tag in change["capabilities_new"] + change["capabilities_modified"]:
            assert tag == tag.lower()
            assert " " not in tag
