from click.testing import CliRunner
from opencg_ingestion.cli import main
from opencg_ingestion.pipeline_runner import IngestionSummary


def test_git_cli_rejects_non_positive_limits():
    runner = CliRunner()

    result = runner.invoke(main, ["git", "https://example.com/repo.git", "--max-chunks", "0"])

    assert result.exit_code == 2
    assert "--max-chunks" in result.output


def test_git_cli_reports_limits_and_truncation(monkeypatch):
    monkeypatch.setattr("opencg_ingestion.cli.load_config", lambda: object())
    monkeypatch.setattr(
        "opencg_ingestion.cli.run_sync",
        lambda *args, **kwargs: IngestionSummary(
            parents=1,
            chunks=2,
            document_limit=1,
            chunk_limit=2,
            documents_truncated=True,
            chunks_truncated=True,
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "git",
            "https://example.com/repo.git",
            "--max-documents",
            "1",
            "--max-chunks",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "limits=max_documents=1,max_chunks=2" in result.output
    assert "truncated=documents,chunks" in result.output
