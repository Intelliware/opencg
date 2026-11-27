#!/usr/bin/env python3
"""Check that ROADMAP.md is well formed and in step with openspec/changes/.

Run by `make check-roadmap` (part of `make ci-static` and the CI `static` job).
Prints one line per problem, naming the item and the fix, and exits 1 if any.

Rules:
- items are `### <id>` headings under `## Now`, `## Next` or `## Later`;
- every item has Status, Size, Capabilities, Depends on and Source fields, a
  **Problem:** and a **Scope:**, and no unknown field;
- IDs are kebab-case and unique; Status is ready, proposed or in-progress; Size
  is S, M or L;
- capabilities exist in openspec/specs/ or an in-flight change, or are `new: <name>`;
- `Depends on` is `none` or roadmap / archived change IDs;
- proposed / in-progress items have openspec/changes/<id>/; ready items don't;
- no item's change is archived (openspec/changes/archive/<date>-<id>/);
- every in-flight change has an item.

Usage: python scripts/check-roadmap.py [ROOT]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BANDS = ("Now", "Next", "Later")
REQUIRED = ("Status", "Size", "Capabilities", "Depends on", "Source")
OPTIONAL = ("Owner", "Issue")
STATUSES = ("ready", "proposed", "in-progress")
SIZES = ("S", "M", "L")
ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
FIELD_RE = re.compile(r"^- \*\*(?P<name>[^*]+?):\*\*\s*(?P<value>.*)$")
ARCHIVED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(?P<id>.+)$")


@dataclass
class Item:
    id: str
    band: str | None
    line: int
    fields: dict[str, str] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)


def parse(text: str) -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    problems: list[str] = []
    band: str | None = None
    current: Item | None = None
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if line.startswith("## "):
            title = line[3:].strip()
            band = title if title in BANDS else None
            current = None
        elif line.startswith("### "):
            current = Item(id=line[4:].strip(), band=band, line=n)
            items.append(current)
        elif current is not None:
            m = FIELD_RE.match(line)
            if m and not current.body:
                name = m["name"].strip()
                if name in current.fields:
                    problems.append(f"ROADMAP.md:{n}: {current.id}: field '{name}' appears twice")
                current.fields[name] = m["value"].strip()
            elif line.strip():
                current.body.append(line)
    return items, problems


def check(root: Path) -> list[str]:
    roadmap = root / "ROADMAP.md"
    if not roadmap.is_file():
        return ["ROADMAP.md is missing"]
    items, problems = parse(roadmap.read_text(encoding="utf-8"))

    changes_dir = root / "openspec" / "changes"
    in_flight = (
        {p.name for p in changes_dir.iterdir() if p.is_dir() and p.name != "archive"}
        if changes_dir.is_dir()
        else set()
    )
    archive_dir = changes_dir / "archive"
    archived = {
        m["id"]
        for p in (archive_dir.iterdir() if archive_dir.is_dir() else [])
        if p.is_dir() and (m := ARCHIVED_RE.match(p.name))
    }
    specs_dir = root / "openspec" / "specs"
    capabilities = (
        {p.name for p in specs_dir.iterdir() if p.is_dir()} if specs_dir.is_dir() else set()
    )
    for name in in_flight:
        delta = changes_dir / name / "specs"
        if delta.is_dir():
            capabilities |= {p.name for p in delta.iterdir() if p.is_dir()}

    ids = [i.id for i in items]
    known = set(ids) | archived
    seen: set[str] = set()
    for item in items:
        where = f"ROADMAP.md:{item.line}: {item.id}"
        if item.band is None:
            problems.append(f"{where}: put the item under '## Now', '## Next' or '## Later'")
        if not ID_RE.match(item.id):
            problems.append(
                f"{where}: the ID must be kebab-case (it becomes the OpenSpec change name)"
            )
        if item.id in seen:
            problems.append(f"{where}: duplicate ID; merge or rename the items")
        seen.add(item.id)

        for name in REQUIRED:
            if not item.fields.get(name):
                problems.append(f"{where}: add '- **{name}:** …'")
        for name in item.fields:
            if name not in REQUIRED + OPTIONAL:
                problems.append(f"{where}: unknown field '{name}'")
        body = "\n".join(item.body)
        for marker in ("**Problem:**", "**Scope:**"):
            if marker not in body:
                problems.append(f"{where}: add a {marker} paragraph")

        status = item.fields.get("Status", "")
        if status and status not in STATUSES:
            problems.append(f"{where}: Status must be one of {', '.join(STATUSES)}, not '{status}'")
        size = item.fields.get("Size", "")
        if size and size not in SIZES:
            problems.append(f"{where}: Size must be S, M or L, not '{size}'")

        for cap in filter(
            None, (c.strip() for c in item.fields.get("Capabilities", "").split(","))
        ):
            if cap.startswith("new:"):
                continue
            if cap not in capabilities:
                problems.append(
                    f"{where}: capability '{cap}' is not in openspec/specs/ or an in-flight change; "
                    f"fix the name or write 'new: {cap}'"
                )

        depends = item.fields.get("Depends on", "")
        if depends and depends != "none":
            for dep in (d.strip() for d in depends.split(",")):
                if dep not in known:
                    problems.append(
                        f"{where}: depends on '{dep}', which is not a roadmap item or archived change"
                    )
                elif dep == item.id:
                    problems.append(f"{where}: an item can't depend on itself")

        if item.id in archived:
            problems.append(f"{where}: the change is archived (shipped); delete the item")
        elif status in ("proposed", "in-progress") and item.id not in in_flight:
            problems.append(
                f"{where}: is {status} but openspec/changes/{item.id}/ doesn't exist; "
                "create the change or set the item back to ready"
            )
        elif status == "ready" and item.id in in_flight:
            problems.append(f"{where}: openspec/changes/{item.id}/ exists; set Status to proposed")

    for name in sorted(in_flight - set(ids)):
        problems.append(
            f"openspec/changes/{name}/ has no roadmap item; add '### {name}' to ROADMAP.md "
            "with Status proposed or in-progress"
        )
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    problems = check(root)
    for p in problems:
        print(f"✗ {p}", file=sys.stderr)
    if problems:
        return 1
    print("✓ ROADMAP.md is well formed and matches openspec/changes/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
