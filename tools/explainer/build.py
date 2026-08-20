#!/usr/bin/env python3
"""Build the interactive architecture explainer.

    python3 tools/explainer/build.py              # rebuild, snapshot if changed
    python3 tools/explainer/build.py --force      # snapshot even if unchanged
    python3 tools/explainer/build.py --check      # exit 1 if stale (for CI)

Reads hand-authored pillar markdown from `content/` and joins it against the
OpenSpec history in `openspec/` on capability tags, producing:

    docs/explainer/index.html                 self-contained, every version inlined
    docs/explainer/versions/NNNN-DATE.json    one snapshot per content change
    docs/explainer/versions/index.json        manifest

Stdlib only: this must run on a bare checkout with no venv and no network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diagram
from content_reader import read_pillars
from openspec_reader import read_all as read_openspec

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parent.parent
CONTENT_DIR = TOOL_DIR / "content"
ASSETS_DIR = TOOL_DIR / "assets"
OPENSPEC_DIR = REPO_ROOT / "openspec"
OUT_DIR = REPO_ROOT / "docs" / "explainer"
VERSIONS_DIR = OUT_DIR / "versions"

SCHEMA_VERSION = 1
SNAPSHOT_NAME_RE = re.compile(r"^(\d{4})-(\d{4}-\d{2}-\d{2})\.json$")


def build_data() -> dict:
    """Assemble the full explainer payload from both content sources."""
    pillars = read_pillars(CONTENT_DIR)
    openspec = read_openspec(OPENSPEC_DIR)
    changes = openspec["changes"]

    mapped: set[str] = set()
    for pillar in pillars:
        mapped.update(pillar["capabilities"])
    unmapped = sorted(set(openspec["all_capability_tags"]) - mapped)
    if unmapped:
        # Fail loudly: an unmapped capability means a whole slice of project
        # history would silently vanish from the explainer.
        raise SystemExit(
            "error: these OpenSpec capabilities are not claimed by any pillar: "
            + ", ".join(unmapped)
            + "\n       add them to a pillar's `capabilities:` frontmatter."
        )

    by_name = {c["name"]: c for c in changes}

    for pillar in pillars:
        caps = set(pillar["capabilities"])
        history = []
        for change in changes:
            touched = caps.intersection(change["capabilities_new"] + change["capabilities_modified"])
            if not touched:
                continue
            deltas = [d for d in change["deltas"] if d["capability"] in caps]
            history.append(
                {
                    "name": change["name"],
                    "date": change["date"],
                    "status": change["status"],
                    "archived": change["archived"],
                    "why": change["why"],
                    "what_changes": change["what_changes"],
                    "tasks_done": change["tasks_done"],
                    "tasks_total": change["tasks_total"],
                    "capabilities_touched": sorted(touched),
                    "introduced": bool(caps.intersection(change["capabilities_new"])),
                    "deltas": deltas,
                    "scenario_count": sum(len(d["scenarios"]) for d in deltas),
                }
            )
        pillar["changes"] = history
        pillar["change_count"] = len(history)
        pillar["shipped_change_count"] = sum(1 for h in history if h["status"] == "shipped")
        pillar["requirement_count"] = sum(len(h["deltas"]) for h in history)
        pillar["scenario_count"] = sum(h["scenario_count"] for h in history)

    shipped = [c for c in changes if c["status"] == "shipped"]
    in_flight = [c for c in changes if c["status"] == "in-flight"]
    not_started = [c for c in changes if c["status"] == "not-started"]

    stats = {
        "pillars": len(pillars),
        "pillars_shipped": sum(1 for p in pillars if p["status"] == "shipped"),
        "capabilities": len(openspec["all_capability_tags"]),
        "changes_total": len(changes),
        "changes_shipped": len(shipped),
        "changes_in_flight": len(in_flight),
        "changes_not_started": len(not_started),
        "tasks_done": sum(c["tasks_done"] for c in changes),
        "tasks_total": sum(c["tasks_total"] for c in changes),
        "requirements": sum(len(c["requirements"]) for c in openspec["capabilities"]),
        "scenarios": sum(c["scenario_count"] for c in openspec["capabilities"]),
        "known_gaps": sum(len(p["gaps"]) for p in pillars),
        "flow_steps": sum(len(p["flow"]) for p in pillars),
    }

    timeline = sorted(
        (c for c in changes if c["date"]),
        key=lambda c: (c["date"], c["name"]),
    )

    return {
        "schema": SCHEMA_VERSION,
        "project": {
            "name": "openCG",
            "full_name": "Open Context Graph",
            "tagline": "A self-hostable context pipeline that exposes a private knowledge "
                       "catalogue to any AI tool over MCP, and logs every byte it hands over.",
        },
        "stats": stats,
        "pillars": pillars,
        "changes": changes,
        "timeline": [c["name"] for c in timeline],
        "capabilities": openspec["capabilities"],
        "diagram": diagram.as_dict(),
        "change_index": sorted(by_name),
    }


def content_hash(data: dict) -> str:
    """Hash the payload, ignoring fields that change on every run."""
    stable = {k: v for k, v in data.items() if k != "generated_at"}
    blob = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_manifest() -> dict:
    manifest_path = VERSIONS_DIR / "index.json"
    if manifest_path.is_file():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"versions": []}


def load_snapshots(manifest: dict) -> list[dict]:
    """Load every snapshot body referenced by the manifest, oldest first."""
    snapshots = []
    for entry in manifest.get("versions", []):
        path = VERSIONS_DIR / entry["file"]
        if not path.is_file():
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        snapshots.append(
            {
                "seq": entry["seq"],
                "label": entry["label"],
                "date": entry["date"],
                "hash": entry["hash"],
                "generated_at": entry.get("generated_at"),
                "summary": entry.get("summary", {}),
                "data": body,
            }
        )
    snapshots.sort(key=lambda s: s["seq"])
    return snapshots


def _summary(data: dict) -> dict:
    keys = ("pillars", "changes_shipped", "changes_total", "tasks_done", "tasks_total", "known_gaps")
    return {k: data["stats"][k] for k in keys}


def write_snapshot(data: dict, manifest: dict, digest: str) -> dict:
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    seq = max((v["seq"] for v in manifest.get("versions", [])), default=0) + 1
    today = date.today().isoformat()
    filename = f"{seq:04d}-{today}.json"

    body = dict(data)
    body["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    body["version"] = {"seq": seq, "label": f"v{seq}", "date": today, "hash": digest}

    (VERSIONS_DIR / filename).write_text(
        json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    entry = {
        "seq": seq,
        "label": f"v{seq}",
        "date": today,
        "file": filename,
        "hash": digest,
        "generated_at": body["generated_at"],
        "summary": _summary(data),
    }
    manifest.setdefault("versions", []).append(entry)
    manifest["versions"].sort(key=lambda v: v["seq"])
    manifest["latest"] = seq
    (VERSIONS_DIR / "index.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entry


def render_html(snapshots: list[dict]) -> str:
    shell = (ASSETS_DIR / "shell.html").read_text(encoding="utf-8")
    css = (ASSETS_DIR / "app.css").read_text(encoding="utf-8")
    js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "versions": [
            {
                "seq": s["seq"],
                "label": s["label"],
                "date": s["date"],
                "hash": s["hash"],
                "summary": s["summary"],
                "data": s["data"],
            }
            for s in snapshots
        ],
    }

    # `</script>` inside JSON would close the host tag early; escaping the slash
    # keeps the value identical to JSON.parse while staying inert to the parser.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    return (
        shell.replace("/*{{CSS}}*/", css)
        .replace("/*{{DATA}}*/", blob)
        .replace("/*{{JS}}*/", js)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the openCG architecture explainer.")
    parser.add_argument("--force", action="store_true", help="snapshot a new version even if unchanged")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the newest snapshot is stale; writes nothing",
    )
    args = parser.parse_args(argv)

    data = build_data()
    digest = content_hash(data)
    manifest = load_manifest()
    versions = manifest.get("versions", [])
    latest_hash = versions[-1]["hash"] if versions else None

    if args.check:
        if latest_hash == digest:
            print(f"explainer up to date ({len(versions)} version(s), hash {digest[:12]})")
            return 0
        if latest_hash is None:
            print("explainer has never been built. run: make explainer", file=sys.stderr)
        else:
            print(
                "explainer is stale: content has changed since "
                f"{versions[-1]['label']} ({versions[-1]['date']}). run: make explainer",
                file=sys.stderr,
            )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if latest_hash == digest and not args.force:
        print(f"content unchanged; keeping {versions[-1]['label']} ({len(versions)} total)")
    else:
        entry = write_snapshot(data, manifest, digest)
        if latest_hash is None:
            print(f"created {entry['label']} ({entry['file']}) — first version")
        elif args.force:
            print(f"created {entry['label']} ({entry['file']}) — forced")
        else:
            print(f"created {entry['label']} ({entry['file']}) — content changed")

    snapshots = load_snapshots(manifest)
    if not snapshots:
        print("error: no snapshots to render", file=sys.stderr)
        return 1

    html = render_html(snapshots)
    out_file = OUT_DIR / "index.html"
    out_file.write_text(html, encoding="utf-8")

    stats = data["stats"]
    size_kb = out_file.stat().st_size / 1024
    print(
        f"wrote {out_file.relative_to(REPO_ROOT)} ({size_kb:.0f} KB) — "
        f"{stats['pillars']} pillars, {stats['flow_steps']} flow steps, "
        f"{stats['changes_total']} changes, {len(snapshots)} version(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
