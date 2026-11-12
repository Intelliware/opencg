"""Endpoint smoke tests for the ingestion HTTP server.

We stub the actual ingest function so tests run in isolation and exercise
the routing + background-task orchestration only.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from opencg_ingestion import server as srv
from opencg_ingestion.runs import RunStore
from opencg_shared import openCGConfig


@pytest.fixture
def make_client(monkeypatch):
    """Return a function that builds a TestClient with a stubbed ingest function."""

    def _build(ingest: Callable | None = None):
        app = srv.app

        async def default_ingest(repo_url: str, cfg: openCGConfig, **_kwargs):
            return (1, 2)

        async def chosen_ingest(repo_url: str, cfg: openCGConfig, **_kwargs):
            if ingest is None:
                return await default_ingest(repo_url, cfg)
            return await ingest(repo_url, cfg)

        monkeypatch.setattr(srv, "ingest_run", chosen_ingest)
        # Pre-populate the state the lifespan would normally set up so we can
        # use a synchronous TestClient without spinning up Postgres.
        # example.com is allow-listed so tests never depend on live DNS.
        app.state.cfg = openCGConfig.model_validate(
            {"ingestion": {"git": {"allowed_hosts": ["example.com"]}}}
        )
        app.state.runs = RunStore(cap=10)
        return TestClient(app)

    return _build


def test_healthz(make_client):
    client = make_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_connectors_lists_git_supported_others_deferred(make_client):
    client = make_client()
    resp = client.get("/connectors")
    assert resp.status_code == 200
    by_name = {c["name"]: c for c in resp.json()}
    assert by_name["git"]["supported"] is True
    for n in ("confluence", "custom-api", "web"):
        assert by_name[n]["supported"] is False
        assert by_name[n]["reason"].startswith("deferred:")


def test_run_git_then_runs_recent_reflects_success(make_client):
    client = make_client()
    resp = client.post("/run/git", json={"repo_url": "https://example.com/x.git"})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    # FastAPI TestClient runs background tasks before returning. So we should
    # already see the terminal state on the next request.
    listed = client.get("/runs/recent").json()
    assert listed[0]["run_id"] == run_id
    # Wait briefly in case scheduling jitter delays the bg task callback.
    deadline = time.monotonic() + 2.0
    while listed[0]["status"] not in ("succeeded", "failed") and time.monotonic() < deadline:
        listed = client.get("/runs/recent").json()
    assert listed[0]["status"] == "succeeded"
    assert listed[0]["parents"] == 1
    assert listed[0]["chunks"] == 2
    assert listed[0]["finished_at"] is not None


def test_run_git_failure_records_error(make_client):
    async def failing(repo_url: str, cfg: openCGConfig):
        raise RuntimeError("clone refused")

    client = make_client(ingest=failing)
    resp = client.post("/run/git", json={"repo_url": "https://example.com/x.git"})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    deadline = time.monotonic() + 2.0
    listed = client.get("/runs/recent").json()
    while listed[0]["status"] not in ("succeeded", "failed") and time.monotonic() < deadline:
        listed = client.get("/runs/recent").json()
    assert listed[0]["run_id"] == run_id
    assert listed[0]["status"] == "failed"
    assert "clone refused" in (listed[0]["error"] or "")


def test_run_git_validates_repo_url(make_client):
    client = make_client()
    resp = client.post("/run/git", json={"repo_url": "x"})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "repo_url",
    ["--upload-pack=touch /tmp/x", "file:///etc", "http://example.com/x.git", "/etc/passwd"],
)
def test_run_git_rejects_unsafe_repo_url_without_creating_a_run(make_client, repo_url):
    client = make_client()
    resp = client.post("/run/git", json={"repo_url": repo_url})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "repo_url_rejected"
    assert client.get("/runs/recent").json() == []


def test_metrics_serves_multiprocess_registry(make_client, monkeypatch, tmp_path):
    """CLI runs write to PROMETHEUS_MULTIPROC_DIR; the server's /metrics sums them."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    code = (
        "from opencg_shared.metrics import record_ingestion_run;"
        "record_ingestion_run(connector='git', status='succeeded', documents=4, chunks=9)"
    )
    subprocess.run([sys.executable, "-c", code], env=env, check=True)
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    resp = make_client().get("/metrics")
    assert resp.status_code == 200
    assert 'opencg_ingestion_runs_total{connector="git",status="succeeded"} 1.0' in resp.text
    assert 'opencg_ingestion_documents_total{connector="git"} 4.0' in resp.text
