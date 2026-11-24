"""Unit tests for scripts/check-dashboards.py (run by `make test-scripts`)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent
BROKEN = Path(__file__).resolve().parent / "fixtures" / "broken-dashboards"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_dashboards", SCRIPTS / "check-dashboards.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cd = _load()


@pytest.fixture(scope="module")
def known() -> set[str]:
    return cd.known_metric_names()


def test_known_names_come_from_the_shared_module(known: set[str]) -> None:
    # Families every service relies on, with their exposed sample suffixes.
    assert "opencg_tokens_total" in known
    assert "opencg_requests_total" in known
    assert "opencg_stage_latency_seconds_bucket" in known
    assert "opencg_stage_latency_seconds_count" in known
    # A bare counter or histogram name is never an exposed series.
    assert "opencg_tokens" not in known
    assert "opencg_stage_latency_seconds" not in known


def test_shipped_dashboards_pass(known: set[str]) -> None:
    files = sorted((ROOT / "infra" / "grafana" / "dashboards").glob("*.json"))
    assert len(files) == 6
    assert cd.check_dashboards(files, known) == []


def test_invalid_json_is_reported(known: set[str]) -> None:
    errors = cd.check_dashboard(BROKEN / "not-json.json", known)
    assert len(errors) == 1 and "invalid JSON" in errors[0]


def test_missing_uid_is_reported(known: set[str]) -> None:
    errors = cd.check_dashboard(BROKEN / "no-uid.json", known)
    assert errors == ["no-uid.json: missing a stable `uid`"]


def test_foreign_datasource_uid_is_reported(known: set[str]) -> None:
    errors = cd.check_dashboard(BROKEN / "bad-datasource.json", known)
    assert len(errors) == 1 and "some-other-prometheus" in errors[0]


def test_undefined_metric_is_reported(known: set[str]) -> None:
    errors = cd.check_dashboard(BROKEN / "unknown-metric.json", known)
    assert len(errors) == 2
    assert any("opencg_definitely_not_a_metric_total" in e for e in errors)
    assert any("queries opencg_tokens," in e for e in errors)


def test_duplicate_uid_is_reported(tmp_path: Path, known: set[str]) -> None:
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps({"uid": "same", "panels": []}))
    errors = cd.check_dashboards(sorted(tmp_path.glob("*.json")), known)
    assert errors == ["b.json: uid 'same' already used by a.json"]


def test_main_fails_on_the_broken_fixture_directory(capsys: pytest.CaptureFixture[str]) -> None:
    assert cd.main(["--no-promtool", str(BROKEN)]) == 1
    assert "problem(s)" in capsys.readouterr().err


def test_main_passes_on_the_shipped_dashboards() -> None:
    assert cd.main(["--no-promtool"]) == 0
