"""Parse `openspec/` into plain dicts for the architecture explainer.

Stdlib only, on purpose: `make explainer` must work on a bare checkout with no
`uv sync`, no venv, and no network. The `openspec` CLI is used when present
purely as a cross-check on task counts; the parser never depends on it.

Three things get read:

- `changes/<name>/` and `changes/archive/<date>-<name>/` -> a change record
  (why / what / impact / capability tags / task counts / spec deltas)
- `specs/<capability>/spec.md` -> the archived requirement baseline
- each change's `specs/<capability>/spec.md` -> the ADDED / MODIFIED / REMOVED
  requirement deltas that change contributed

The capability tags in `## Capabilities` are the join key the explainer uses to
answer "which spec changes shaped this pillar", so extracting them accurately
matters more than anything else in here.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

ARCHIVE_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")

# `- `capability-name`: prose` at the top level of a Capabilities subsection.
# Nested bullets are indented and must not match.
CAPABILITY_BULLET_RE = re.compile(r"^- +`([a-z0-9][a-z0-9-]*)`")

TASK_DONE_RE = re.compile(r"^\s*- \[[xX]\]")
TASK_OPEN_RE = re.compile(r"^\s*- \[ \]")

REQUIREMENT_RE = re.compile(r"^#{3,4} Requirement: +(.+?)\s*$")
SCENARIO_RE = re.compile(r"^#{4,5} Scenario: +(.+?)\s*$")
DELTA_HEADING_RE = re.compile(r"^## +(ADDED|MODIFIED|REMOVED|RENAMED) +Requirements?\s*$")


@dataclass
class RequirementDelta:
    """One requirement added/modified/removed by a change, for one capability."""

    capability: str
    operation: str  # ADDED | MODIFIED | REMOVED | RENAMED
    requirement: str
    scenarios: list[str] = field(default_factory=list)


@dataclass
class Change:
    """One OpenSpec change: the unit of "what we did to the project"."""

    name: str
    date: str | None  # ISO date from the archive dir prefix; None while in flight
    archived: bool
    status: str  # shipped | in-flight | not-started
    why: str
    what_changes: list[str]
    impact: list[str]
    capabilities_new: list[str]
    capabilities_modified: list[str]
    tasks_done: int
    tasks_total: int
    deltas: list[RequirementDelta]

    @property
    def capabilities(self) -> list[str]:
        seen: list[str] = []
        for cap in self.capabilities_new + self.capabilities_modified:
            if cap not in seen:
                seen.append(cap)
        return seen


@dataclass
class Capability:
    """An archived capability spec: the current authoritative contract."""

    name: str
    requirements: list[str]
    scenario_count: int


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def split_sections(markdown: str) -> dict[str, str]:
    """Split on `## ` headings. Later duplicates win; none exist in practice."""
    sections: dict[str, str] = {}
    current = ""
    buf: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## ") and not line.startswith("## ##"):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def first_paragraph(text: str) -> str:
    """First non-empty paragraph, joined to one line."""
    para: list[str] = []
    for line in text.strip().splitlines():
        if not line.strip():
            if para:
                break
            continue
        para.append(line.strip())
    return " ".join(para)


def top_level_bullets(text: str) -> list[str]:
    """Collect `- ` bullets, folding continuation lines into the bullet.

    Nested bullets (indented) are folded into their parent rather than
    surfaced separately, which keeps the explainer's bullet lists readable.
    """
    bullets: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("- "):
            bullets.append(raw[2:].strip())
        elif raw.startswith("  ") and raw.strip() and bullets:
            bullets[-1] += " " + raw.strip()
    return bullets


def _capability_tags(section: str, heading: str) -> list[str]:
    """Pull capability names from a `### <heading>` subsection of `## Capabilities`."""
    lines = section.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == f"### {heading}".lower():
            start = i + 1
            break
    if start is None:
        return []

    tags: list[str] = []
    for line in lines[start:]:
        if line.startswith("### ") or line.startswith("## "):
            break
        match = CAPABILITY_BULLET_RE.match(line)
        if match and match.group(1) not in tags:
            tags.append(match.group(1))
    return tags


def count_tasks(tasks_md: str) -> tuple[int, int]:
    done = sum(1 for line in tasks_md.splitlines() if TASK_DONE_RE.match(line))
    open_ = sum(1 for line in tasks_md.splitlines() if TASK_OPEN_RE.match(line))
    return done, done + open_


def parse_spec_delta(capability: str, markdown: str) -> list[RequirementDelta]:
    """Parse a change's `specs/<capability>/spec.md` into requirement deltas."""
    deltas: list[RequirementDelta] = []
    operation = "MODIFIED"
    current: RequirementDelta | None = None

    for line in markdown.splitlines():
        delta_heading = DELTA_HEADING_RE.match(line)
        if delta_heading:
            operation = delta_heading.group(1)
            current = None
            continue

        requirement = REQUIREMENT_RE.match(line)
        if requirement:
            current = RequirementDelta(
                capability=capability,
                operation=operation,
                requirement=requirement.group(1),
            )
            deltas.append(current)
            continue

        scenario = SCENARIO_RE.match(line)
        if scenario and current is not None:
            current.scenarios.append(scenario.group(1))

    return deltas


def _parse_change(directory: Path, *, archived: bool) -> Change:
    dir_name = directory.name
    date: str | None = None
    name = dir_name
    if archived:
        match = ARCHIVE_DIR_RE.match(dir_name)
        if match:
            date, name = match.group(1), match.group(2)

    sections = split_sections(_read(directory / "proposal.md"))
    capabilities_section = sections.get("Capabilities", "")

    done, total = count_tasks(_read(directory / "tasks.md"))
    if archived:
        status = "shipped"
    elif done == 0:
        status = "not-started"
    else:
        status = "in-flight"

    deltas: list[RequirementDelta] = []
    specs_dir = directory / "specs"
    if specs_dir.is_dir():
        for capability_dir in sorted(specs_dir.iterdir()):
            spec_file = capability_dir / "spec.md"
            if spec_file.is_file():
                deltas.extend(parse_spec_delta(capability_dir.name, _read(spec_file)))

    return Change(
        name=name,
        date=date,
        archived=archived,
        status=status,
        why=first_paragraph(sections.get("Why", "")),
        what_changes=top_level_bullets(sections.get("What Changes", "")),
        impact=top_level_bullets(sections.get("Impact", "")),
        capabilities_new=_capability_tags(capabilities_section, "New Capabilities"),
        capabilities_modified=_capability_tags(capabilities_section, "Modified Capabilities"),
        tasks_done=done,
        tasks_total=total,
        deltas=deltas,
    )


def _cli_task_counts(openspec_root: Path) -> dict[str, tuple[int, int]]:
    """Ask the `openspec` CLI for active-change task counts. Empty dict if absent."""
    try:
        proc = subprocess.run(
            ["openspec", "list", "--json"],
            cwd=openspec_root.parent,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    return {
        entry["name"]: (entry.get("completedTasks", 0), entry.get("totalTasks", 0))
        for entry in payload.get("changes", [])
        if entry.get("name")
    }


def read_changes(openspec_root: Path) -> list[Change]:
    """All changes, newest first. Active (undated) changes sort ahead of archived."""
    changes_dir = openspec_root / "changes"
    changes: list[Change] = []

    if changes_dir.is_dir():
        for entry in sorted(changes_dir.iterdir()):
            if entry.is_dir() and entry.name != "archive":
                changes.append(_parse_change(entry, archived=False))

        archive_dir = changes_dir / "archive"
        if archive_dir.is_dir():
            for entry in sorted(archive_dir.iterdir()):
                if entry.is_dir():
                    changes.append(_parse_change(entry, archived=True))

    # The CLI is authoritative for in-flight counts if it happens to be installed;
    # our own tasks.md parse is the fallback and matches it in practice.
    cli_counts = _cli_task_counts(openspec_root)
    for change in changes:
        if not change.archived and change.name in cli_counts:
            done, total = cli_counts[change.name]
            if total:
                change.tasks_done, change.tasks_total = done, total
                change.status = "not-started" if done == 0 else "in-flight"

    changes.sort(key=lambda c: (c.date or "9999-99-99", c.name), reverse=True)
    return changes


def read_capabilities(openspec_root: Path) -> list[Capability]:
    """The archived spec baseline under `openspec/specs/`."""
    specs_dir = openspec_root / "specs"
    capabilities: list[Capability] = []
    if not specs_dir.is_dir():
        return capabilities

    for entry in sorted(specs_dir.iterdir()):
        spec_file = entry / "spec.md"
        if not entry.is_dir() or not spec_file.is_file():
            continue
        markdown = _read(spec_file)
        requirements = [
            m.group(1) for m in (REQUIREMENT_RE.match(line) for line in markdown.splitlines()) if m
        ]
        scenarios = sum(1 for line in markdown.splitlines() if SCENARIO_RE.match(line))
        capabilities.append(
            Capability(name=entry.name, requirements=requirements, scenario_count=scenarios)
        )
    return capabilities


def read_all(openspec_root: Path) -> dict:
    """Everything the explainer needs from `openspec/`, JSON-ready."""
    changes = read_changes(openspec_root)
    capabilities = read_capabilities(openspec_root)

    tagged: set[str] = set()
    for change in changes:
        tagged.update(change.capabilities)

    return {
        "changes": [asdict(c) for c in changes],
        "capabilities": [asdict(c) for c in capabilities],
        "all_capability_tags": sorted(tagged),
    }
