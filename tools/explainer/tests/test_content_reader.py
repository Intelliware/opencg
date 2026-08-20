"""Tests for the pillar markdown parser.

The parser is the contract for anyone authoring a new pillar, so the escaping
and structural rules are pinned down here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from content_reader import (
    parse_flow,
    parse_frontmatter,
    parse_pillar,
    read_pillars,
    render_inline,
)

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"

PILLAR = """\
---
id: sample
title: Sample Pillar
capabilities: alpha, beta
status: partial
services: pipeline, ingestion
tagline: A one-line summary with `code`.
---

## What it is

First paragraph.

Second paragraph with **bold** text.

## Why it exists

Because it does.

## Flow

### 1. First step
Does the first thing.
file: services/a/one.py

### 2. Second step
Does the second thing across
two source lines.
file: services/b/two.py, services/b/three.py

### 3. Step with no file
Nothing to point at.

## Facts
- Port: **8100**
- Model: `nomic-embed-text`

## Gaps
- **Nothing works.** Not even a little.
- A second gap
  wrapped onto two lines.
"""


# ---------------------------------------------------------------- inline rendering


def test_render_inline_handles_code_bold_and_links():
    out = render_inline("A `code` and **bold** and [link](http://x/y).")
    assert out == 'A <code>code</code> and <strong>bold</strong> and <a href="http://x/y">link</a>.'


def test_render_inline_escapes_html_before_formatting():
    assert render_inline("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_render_inline_escapes_inside_code_spans():
    # A tag written inside backticks must render as visible text, not markup.
    assert render_inline("`<b>`") == "<code>&lt;b&gt;</code>"


def test_render_inline_escapes_ampersands():
    assert render_inline("a & b") == "a &amp; b"


def test_render_inline_on_empty_input():
    assert render_inline("") == ""


# ---------------------------------------------------------------- frontmatter


def test_parse_frontmatter_splits_meta_from_body():
    meta, body = parse_frontmatter(PILLAR)
    assert meta["id"] == "sample"
    assert meta["title"] == "Sample Pillar"
    assert meta["capabilities"] == "alpha, beta"
    assert body.lstrip().startswith("## What it is")


def test_parse_frontmatter_keeps_colons_in_values():
    meta, _ = parse_frontmatter("---\nid: x\ntagline: Reads http://a/b: really\n---\nbody\n")
    assert meta["tagline"] == "Reads http://a/b: really"


def test_parse_frontmatter_absent_returns_whole_body():
    meta, body = parse_frontmatter("## Heading\n\nText.\n")
    assert meta == {}
    assert body.startswith("## Heading")


# ---------------------------------------------------------------- flow


def test_parse_flow_numbers_titles_and_files():
    steps = parse_flow(parse_frontmatter(PILLAR)[1].split("## Flow")[1].split("## Facts")[0])
    assert [s.index for s in steps] == [1, 2, 3]
    assert [s.title for s in steps] == ["First step", "Second step", "Step with no file"]
    assert steps[0].files == ["services/a/one.py"]
    assert steps[1].files == ["services/b/two.py", "services/b/three.py"]
    assert steps[2].files == []


def test_parse_flow_folds_wrapped_detail_into_one_paragraph():
    steps = parse_flow("### 1. T\nDoes the second thing across\ntwo source lines.\n")
    assert steps[0].detail == "<p>Does the second thing across two source lines.</p>"


def test_parse_flow_keeps_the_file_line_out_of_the_detail():
    steps = parse_flow("### 1. T\nProse.\nfile: a/b.py\n")
    assert "file:" not in steps[0].detail
    assert steps[0].files == ["a/b.py"]


def test_parse_flow_infers_index_when_unnumbered():
    steps = parse_flow("### Alpha\nOne.\n\n### Beta\nTwo.\n")
    assert [(s.index, s.title) for s in steps] == [(1, "Alpha"), (2, "Beta")]


def test_parse_flow_on_empty_input():
    assert parse_flow("") == []


# ---------------------------------------------------------------- whole pillar


@pytest.fixture()
def sample(tmp_path):
    path = tmp_path / "07-sample.md"
    path.write_text(PILLAR, encoding="utf-8")
    return parse_pillar(path)


def test_parse_pillar_reads_metadata(sample):
    assert sample.id == "sample"
    assert sample.title == "Sample Pillar"
    assert sample.capabilities == ["alpha", "beta"]
    assert sample.services == ["pipeline", "ingestion"]
    assert sample.status == "partial"
    assert sample.tagline == "A one-line summary with <code>code</code>."


def test_parse_pillar_order_comes_from_the_filename_prefix(sample):
    assert sample.order == 7


def test_parse_pillar_splits_prose_into_paragraphs(sample):
    assert sample.what.count("<p>") == 2
    assert "<strong>bold</strong>" in sample.what


def test_parse_pillar_reads_facts_and_gaps(sample):
    assert sample.facts == ["Port: <strong>8100</strong>", "Model: <code>nomic-embed-text</code>"]
    assert sample.gaps[0].startswith("<strong>Nothing works.</strong>")
    assert sample.gaps[1] == "A second gap wrapped onto two lines."


def test_parse_pillar_requires_id_and_title(tmp_path):
    missing_id = tmp_path / "01-x.md"
    missing_id.write_text("---\ntitle: T\n---\n\n## What it is\nx\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required `id`"):
        parse_pillar(missing_id)

    missing_title = tmp_path / "02-y.md"
    missing_title.write_text("---\nid: y\n---\n\n## What it is\nx\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required `title`"):
        parse_pillar(missing_title)


def test_parse_pillar_tolerates_missing_optional_sections(tmp_path):
    path = tmp_path / "03-min.md"
    path.write_text("---\nid: min\ntitle: Min\n---\n", encoding="utf-8")
    pillar = parse_pillar(path)
    assert pillar.flow == [] and pillar.facts == [] and pillar.gaps == []
    assert pillar.what == "" and pillar.why == ""


def test_read_pillars_orders_by_filename_prefix(tmp_path):
    (tmp_path / "02-b.md").write_text("---\nid: b\ntitle: B\n---\n", encoding="utf-8")
    (tmp_path / "01-a.md").write_text("---\nid: a\ntitle: A\n---\n", encoding="utf-8")
    (tmp_path / "10-c.md").write_text("---\nid: c\ntitle: C\n---\n", encoding="utf-8")
    assert [p["id"] for p in read_pillars(tmp_path)] == ["a", "b", "c"]


def test_read_pillars_rejects_duplicate_ids(tmp_path):
    (tmp_path / "01-a.md").write_text("---\nid: dup\ntitle: A\n---\n", encoding="utf-8")
    (tmp_path / "02-b.md").write_text("---\nid: dup\ntitle: B\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate pillar id"):
        read_pillars(tmp_path)


# ---------------------------------------------------------------- real content


def test_real_pillar_content_is_well_formed():
    """Every shipped pillar file must parse and carry the sections readers rely on."""
    pillars = read_pillars(CONTENT_DIR)
    assert len(pillars) >= 10

    for pillar in pillars:
        label = pillar["id"]
        assert pillar["title"], f"{label}: no title"
        assert pillar["tagline"], f"{label}: no tagline"
        assert pillar["what"], f"{label}: no 'What it is'"
        assert pillar["flow"], f"{label}: no flow steps"
        assert pillar["capabilities"], f"{label}: claims no capability"
        assert pillar["status"] in {"shipped", "partial", "planned"}, f"{label}: odd status"

        # Flow steps are the load-bearing content; each needs real detail.
        indices = [s["index"] for s in pillar["flow"]]
        assert indices == sorted(indices), f"{label}: flow steps out of order"
        for step in pillar["flow"]:
            assert step["title"], f"{label}: step {step['index']} has no title"
            assert step["detail"], f"{label}: step {step['index']} has no detail"

        # Cited paths must actually exist, or the explainer sends readers nowhere.
        for step in pillar["flow"]:
            for ref in step["files"]:
                assert (CONTENT_DIR.parents[2] / ref).exists(), f"{label}: missing path {ref}"
