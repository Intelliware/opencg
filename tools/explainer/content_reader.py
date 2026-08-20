"""Parse the hand-authored pillar markdown files.

Format, one file per pillar in `content/`:

    ---
    id: ingestion
    title: Ingestion
    capabilities: ingestion, catalog-store
    status: partial
    tagline: One line shown under the title.
    ---

    ## What it is
    Free prose. Blank-line separated paragraphs.

    ## Why it exists
    More prose.

    ## Flow

    ### 1. Clone the repo
    Prose describing the step.
    file: services/ingestion/src/opencg_ingestion/connectors/git.py

    ## Facts
    - Only connector: git
    - Max file size: 1 MB

    ## Gaps
    - No PDF or OCR path.

Only `id` and `title` are required. `## Flow` steps are `### N. Title` blocks;
a trailing `file:` line (or several) becomes a code-path link on the step. Prose
supports inline `code`, **bold**, and [links](path) via `render_inline`.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
STEP_HEADING_RE = re.compile(r"^### +(?:(\d+)\.\s*)?(.+?)\s*$")
FILE_LINE_RE = re.compile(r"^file:\s*(.+?)\s*$", re.IGNORECASE)

# Inline markdown, applied after HTML escaping so authored text can never
# inject markup into the generated page.
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass
class FlowStep:
    index: int
    title: str
    detail: str
    files: list[str] = field(default_factory=list)


@dataclass
class Pillar:
    id: str
    title: str
    order: int
    capabilities: list[str]
    status: str
    tagline: str
    what: str
    why: str
    flow: list[FlowStep]
    facts: list[str]
    gaps: list[str]
    services: list[str]
    stores: list[str]


def render_inline(text: str) -> str:
    """Escape HTML, then apply inline `code`, **bold**, and [links](target)."""
    out = html.escape(text, quote=False)
    out = _CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)
    return out


def parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown

    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, markdown[match.end() :]


def _sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = ""
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def _paragraphs(text: str) -> str:
    """Collapse a prose block into `<p>` HTML."""
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in text.strip().splitlines():
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return "".join(f"<p>{render_inline(' '.join(p))}</p>" for p in paragraphs)


def _bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("- "):
            bullets.append(raw[2:].strip())
        elif raw.startswith("  ") and raw.strip() and bullets:
            bullets[-1] += " " + raw.strip()
    return [render_inline(b) for b in bullets]


def parse_flow(text: str) -> list[FlowStep]:
    """Split a `## Flow` body into `### N. Title` steps."""
    steps: list[FlowStep] = []
    heading: str | None = None
    explicit_index: int | None = None
    buf: list[str] = []

    def flush() -> None:
        if heading is None:
            return
        files: list[str] = []
        detail_lines: list[str] = []
        for line in buf:
            file_match = FILE_LINE_RE.match(line.strip())
            if file_match:
                files.extend(part.strip() for part in file_match.group(1).split(",") if part.strip())
            else:
                detail_lines.append(line)
        steps.append(
            FlowStep(
                index=explicit_index if explicit_index is not None else len(steps) + 1,
                title=render_inline(heading),
                detail=_paragraphs("\n".join(detail_lines)),
                files=files,
            )
        )

    for line in text.splitlines():
        match = STEP_HEADING_RE.match(line)
        if match:
            flush()
            explicit_index = int(match.group(1)) if match.group(1) else None
            heading = match.group(2)
            buf = []
        elif heading is not None:
            buf.append(line)
    flush()
    return steps


def _split_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_pillar(path: Path) -> Pillar:
    markdown = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(markdown)
    sections = _sections(body)

    pillar_id = meta.get("id") or path.stem
    if "id" not in meta:
        raise ValueError(f"{path}: frontmatter is missing required `id`")
    if "title" not in meta:
        raise ValueError(f"{path}: frontmatter is missing required `title`")

    # Numeric filename prefix drives sidebar order: `03-model-providers.md` -> 3.
    prefix = path.stem.split("-", 1)[0]
    order = int(prefix) if prefix.isdigit() else 999

    return Pillar(
        id=pillar_id,
        title=meta["title"],
        order=order,
        capabilities=_split_list(meta.get("capabilities", "")),
        status=meta.get("status", "shipped"),
        tagline=render_inline(meta.get("tagline", "")),
        what=_paragraphs(sections.get("What it is", "")),
        why=_paragraphs(sections.get("Why it exists", "")),
        flow=parse_flow(sections.get("Flow", "")),
        facts=_bullets(sections.get("Facts", "")),
        gaps=_bullets(sections.get("Gaps", "")),
        services=_split_list(meta.get("services", "")),
        stores=_split_list(meta.get("stores", "")),
    )


def read_pillars(content_dir: Path) -> list[dict]:
    pillars = [parse_pillar(p) for p in sorted(content_dir.glob("*.md"))]
    pillars.sort(key=lambda p: (p.order, p.title))

    seen: set[str] = set()
    for pillar in pillars:
        if pillar.id in seen:
            raise ValueError(f"duplicate pillar id: {pillar.id}")
        seen.add(pillar.id)

    return [asdict(p) for p in pillars]
