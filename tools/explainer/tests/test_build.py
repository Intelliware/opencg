"""Tests for the build orchestration: the join, the hash, and version snapshotting."""

from __future__ import annotations

import json

import build
import pytest

# ---------------------------------------------------------------- hashing


def test_content_hash_ignores_generated_at():
    a = {"stats": {"x": 1}, "generated_at": "2026-01-01T00:00:00+00:00"}
    b = {"stats": {"x": 1}, "generated_at": "2099-12-31T23:59:59+00:00"}
    assert build.content_hash(a) == build.content_hash(b)


def test_content_hash_changes_with_content():
    a = {"stats": {"x": 1}}
    b = {"stats": {"x": 2}}
    assert build.content_hash(a) != build.content_hash(b)


def test_content_hash_is_key_order_independent():
    assert build.content_hash({"a": 1, "b": 2}) == build.content_hash({"b": 2, "a": 1})


# ---------------------------------------------------------------- the real join


@pytest.fixture(scope="module")
def payload():
    return build.build_data()


def test_build_data_produces_pillars_and_changes(payload):
    assert payload["pillars"], "no pillars"
    assert payload["changes"], "no changes"
    assert payload["schema"] == build.SCHEMA_VERSION


def test_every_capability_tag_is_claimed_by_a_pillar(payload):
    """The build raises if a tag is orphaned; this pins the invariant explicitly."""
    claimed = set()
    for pillar in payload["pillars"]:
        claimed.update(pillar["capabilities"])
    for change in payload["changes"]:
        for tag in change["capabilities_new"] + change["capabilities_modified"]:
            assert tag in claimed, f"capability {tag} belongs to no pillar"


def test_pillar_history_only_contains_relevant_changes(payload):
    for pillar in payload["pillars"]:
        caps = set(pillar["capabilities"])
        for change in pillar["changes"]:
            assert caps.intersection(change["capabilities_touched"]), (
                f"{pillar['id']} lists {change['name']} but shares no capability with it"
            )
            for delta in change["deltas"]:
                assert delta["capability"] in caps


def test_pillar_history_is_oldest_first_by_date(payload):
    for pillar in payload["pillars"]:
        dated = [c["date"] for c in pillar["changes"] if c["date"]]
        # `changes` is stored newest-first; the view reverses it for display.
        assert dated == sorted(dated, reverse=True), pillar["id"]


def test_pillar_counts_match_their_history(payload):
    for pillar in payload["pillars"]:
        assert pillar["change_count"] == len(pillar["changes"])
        assert pillar["shipped_change_count"] == sum(
            1 for c in pillar["changes"] if c["status"] == "shipped"
        )
        assert pillar["requirement_count"] == sum(len(c["deltas"]) for c in pillar["changes"])


def test_stats_are_internally_consistent(payload):
    stats = payload["stats"]
    assert stats["pillars"] == len(payload["pillars"])
    assert stats["changes_total"] == len(payload["changes"])
    assert (
        stats["changes_shipped"] + stats["changes_in_flight"] + stats["changes_not_started"]
        == stats["changes_total"]
    )
    assert stats["tasks_done"] <= stats["tasks_total"]
    assert stats["flow_steps"] == sum(len(p["flow"]) for p in payload["pillars"])
    assert stats["known_gaps"] == sum(len(p["gaps"]) for p in payload["pillars"])


def test_diagram_nodes_reference_real_pillars(payload):
    ids = {p["id"] for p in payload["pillars"]}
    for node in payload["diagram"]["nodes"]:
        if node.get("pillar"):
            assert node["pillar"] in ids, f"diagram node {node['id']} points at no pillar"


def test_diagram_edges_reference_real_nodes(payload):
    ids = {n["id"] for n in payload["diagram"]["nodes"]}
    for edge in payload["diagram"]["edges"]:
        assert edge["from"] in ids and edge["to"] in ids


def test_diagram_nodes_do_not_overlap(payload):
    """Overlapping boxes are a layout bug that is easy to introduce by hand."""
    dg = payload["diagram"]
    w, h = dg["node_width"], dg["node_height"]
    nodes = dg["nodes"]
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            overlap_x = a["x"] < b["x"] + w and b["x"] < a["x"] + w
            overlap_y = a["y"] < b["y"] + h and b["y"] < a["y"] + h
            assert not (overlap_x and overlap_y), f"{a['id']} overlaps {b['id']}"


def test_diagram_nodes_fit_the_viewbox(payload):
    dg = payload["diagram"]
    for node in dg["nodes"]:
        assert 0 <= node["x"] <= dg["width"] - dg["node_width"], node["id"]
        assert 0 <= node["y"] <= dg["height"] - dg["node_height"], node["id"]


# ---------------------------------------------------------------- snapshots


def test_snapshot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "VERSIONS_DIR", tmp_path / "versions")

    data = {"schema": 1, "stats": {"pillars": 3, "changes_shipped": 1, "changes_total": 2,
                                   "tasks_done": 5, "tasks_total": 10, "known_gaps": 4}}
    digest = build.content_hash(data)

    manifest = build.load_manifest()
    assert manifest == {"versions": []}

    entry = build.write_snapshot(data, manifest, digest)
    assert entry["seq"] == 1
    assert entry["label"] == "v1"
    assert entry["hash"] == digest
    assert entry["summary"]["pillars"] == 3

    reloaded = build.load_manifest()
    assert len(reloaded["versions"]) == 1
    assert reloaded["latest"] == 1

    snapshots = build.load_snapshots(reloaded)
    assert len(snapshots) == 1
    assert snapshots[0]["data"]["stats"]["pillars"] == 3
    assert snapshots[0]["data"]["version"]["label"] == "v1"


def test_snapshot_sequence_increments(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "VERSIONS_DIR", tmp_path / "versions")
    stats = {"pillars": 1, "changes_shipped": 0, "changes_total": 0,
             "tasks_done": 0, "tasks_total": 0, "known_gaps": 0}

    manifest = build.load_manifest()
    labels = []
    for i in range(3):
        data = {"stats": dict(stats, pillars=i + 1)}
        labels.append(build.write_snapshot(data, manifest, build.content_hash(data))["label"])
    assert labels == ["v1", "v2", "v3"]
    assert [v["seq"] for v in build.load_manifest()["versions"]] == [1, 2, 3]


def test_snapshot_filenames_are_sortable(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "VERSIONS_DIR", tmp_path / "versions")
    stats = {"pillars": 1, "changes_shipped": 0, "changes_total": 0,
             "tasks_done": 0, "tasks_total": 0, "known_gaps": 0}
    manifest = build.load_manifest()
    for i in range(2):
        data = {"stats": dict(stats, pillars=i + 1)}
        build.write_snapshot(data, manifest, build.content_hash(data))
    names = sorted(p.name for p in (tmp_path / "versions").glob("0*.json"))
    assert [build.SNAPSHOT_NAME_RE.match(n).group(1) for n in names] == ["0001", "0002"]


def test_load_manifest_survives_corrupt_json(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "index.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(build, "VERSIONS_DIR", versions)
    assert build.load_manifest() == {"versions": []}


def test_load_snapshots_skips_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "VERSIONS_DIR", tmp_path / "versions")
    manifest = {"versions": [{"seq": 1, "label": "v1", "date": "2026-01-01",
                              "file": "gone.json", "hash": "x"}]}
    assert build.load_snapshots(manifest) == []


# ---------------------------------------------------------------- rendering


def test_render_html_inlines_everything():
    snapshots = [{
        "seq": 1, "label": "v1", "date": "2026-01-01", "hash": "abc",
        "summary": {"pillars": 1}, "data": {"stats": {"pillars": 1}},
    }]
    html = build.render_html(snapshots)

    assert "{{CSS}}" not in html and "{{JS}}" not in html and "{{DATA}}" not in html
    assert "--accent" in html          # stylesheet
    assert "drawDiagram" in html       # application script
    assert '"label": "v1"' in html or '"label":"v1"' in html


def test_render_html_neutralises_closing_script_tags():
    """A `</script>` in the data would end the host tag early and break the page."""
    snapshots = [{
        "seq": 1, "label": "v1", "date": "2026-01-01", "hash": "abc", "summary": {},
        "data": {"note": "danger </script><script>alert(1)</script>"},
    }]
    html = build.render_html(snapshots)
    payload_start = html.index('id="explainer-data"')
    payload_end = html.index("</script>", payload_start)
    payload = html[html.index(">", payload_start) + 1 : payload_end]
    assert "</script" not in payload
    # Escaping the slash must not change the decoded value.
    assert json.loads(payload.replace("<\\/", "</"))["versions"][0]["data"]["note"].startswith(
        "danger </script>"
    )


def test_real_build_output_exists_and_is_current():
    """`make explainer` should have been run; catches a forgotten rebuild."""
    out = build.OUT_DIR / "index.html"
    if not out.exists():
        pytest.skip("no build present; run `make explainer`")
    data = build.build_data()
    manifest = build.load_manifest()
    versions = manifest.get("versions", [])
    assert versions, "index.html exists but no version manifest does"
    assert versions[-1]["hash"] == build.content_hash(data), (
        "docs/explainer is stale; run `make explainer`"
    )


def test_check_mode_reports_up_to_date(capsys):
    out = build.OUT_DIR / "index.html"
    if not out.exists():
        pytest.skip("no build present; run `make explainer`")
    assert build.main(["--check"]) == 0
    assert "up to date" in capsys.readouterr().out
