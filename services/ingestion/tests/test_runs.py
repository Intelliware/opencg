from __future__ import annotations

import pytest
from opencg_ingestion.runs import RunStore


@pytest.mark.asyncio
async def test_add_returns_queued_run_with_timestamps():
    store = RunStore()
    run = await store.add(connector="git", repo="https://x")
    assert run.connector == "git"
    assert run.repo == "https://x"
    assert run.status == "queued"
    assert run.run_id
    assert run.started_at is not None
    assert run.finished_at is None


@pytest.mark.asyncio
async def test_update_status_and_finished_writes_finished_at():
    store = RunStore()
    run = await store.add(connector="git", repo="https://x")

    running = await store.update(run.run_id, status="running")
    assert running is not None
    assert running.status == "running"
    assert running.finished_at is None

    done = await store.update(run.run_id, status="succeeded", parents=5, chunks=23, finished=True)
    assert done is not None
    assert done.status == "succeeded"
    assert done.parents == 5
    assert done.chunks == 23
    assert done.finished_at is not None


@pytest.mark.asyncio
async def test_update_failure_records_error():
    store = RunStore()
    run = await store.add(connector="git", repo="https://x")
    failed = await store.update(run.run_id, status="failed", error="boom", finished=True)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "boom"


@pytest.mark.asyncio
async def test_update_unknown_id_returns_none():
    store = RunStore()
    out = await store.update("missing", status="failed")
    assert out is None


@pytest.mark.asyncio
async def test_list_recent_returns_most_recent_first():
    store = RunStore()
    a = await store.add(connector="git", repo="a")
    b = await store.add(connector="git", repo="b")
    items = await store.list_recent()
    assert [r.run_id for r in items] == [b.run_id, a.run_id]


@pytest.mark.asyncio
async def test_cap_evicts_oldest():
    store = RunStore(cap=3)
    runs = []
    for i in range(5):
        runs.append(await store.add(connector="git", repo=f"r{i}"))
    items = await store.list_recent()
    assert len(items) == 3
    # Newest three are kept; the first two are evicted.
    assert [r.repo for r in items] == ["r4", "r3", "r2"]
