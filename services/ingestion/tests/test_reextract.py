from __future__ import annotations

from datetime import datetime

from click.testing import CliRunner
from opencg_ingestion import cli
from opencg_ingestion.reextract import (
    ReextractSummary,
    current_extractor_version,
    version_is_current_or_newer,
)


def test_version_filter_skips_current_and_newer():
    current = current_extractor_version("gemma3:4b")
    assert version_is_current_or_newer(current, current)
    assert version_is_current_or_newer("text-extractor/v2/other-model", current)
    assert not version_is_current_or_newer("text-extractor/v0/old", current)
    assert not version_is_current_or_newer(None, current)


def test_reextract_cli_passes_filters_and_prints_summary(monkeypatch):
    captured = {}

    def fake_run(cfg, *, source, since):
        captured["source"] = source
        captured["since"] = since
        return ReextractSummary(succeeded=4, failed=1, skipped=2)

    monkeypatch.setattr(cli, "reextract_sync", fake_run)
    result = CliRunner().invoke(
        cli.main,
        ["re-extract", "--source", "git", "--since", "2026-06-01"],
    )

    assert result.exit_code == 0
    assert captured == {
        "source": "git",
        "since": datetime(2026, 6, 1),
    }
    assert "succeeded=4 failed=1 skipped=2" in result.output
