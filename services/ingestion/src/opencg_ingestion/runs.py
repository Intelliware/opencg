"""In-memory run history. Capped, thread-safe via asyncio lock.

Durability across container restarts is explicitly deferred to the
background-enrichment follow-up change (see
openspec/changes/add-admin-vector-and-content/design.md D2).
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

from opencg_shared import IngestionRun, IngestionRunStatus


class RunStore:
    def __init__(self, *, cap: int = 100) -> None:
        self._cap = cap
        self._runs: deque[IngestionRun] = deque(maxlen=cap)
        self._lock = asyncio.Lock()

    async def add(
        self,
        *,
        connector: str,
        repo: str | None,
        classification: str = "internal",
        requested_by: str | None = None,
    ) -> IngestionRun:
        run = IngestionRun(
            run_id=str(uuid4()),
            connector=connector,
            repo=repo,
            started_at=datetime.now(tz=UTC),
            status="queued",
            classification=classification,
            requested_by=requested_by,
        )
        async with self._lock:
            self._runs.appendleft(run)
        return run

    async def update(
        self,
        run_id: str,
        *,
        status: IngestionRunStatus | None = None,
        parents: int | None = None,
        chunks: int | None = None,
        error: str | None = None,
        finished: bool = False,
    ) -> IngestionRun | None:
        async with self._lock:
            for i, r in enumerate(self._runs):
                if r.run_id != run_id:
                    continue
                # Build a new copy because pydantic models are mutable but
                # callers might be iterating.
                updates: dict = {}
                if status is not None:
                    updates["status"] = status
                if parents is not None:
                    updates["parents"] = parents
                if chunks is not None:
                    updates["chunks"] = chunks
                if error is not None:
                    updates["error"] = error
                if finished:
                    updates["finished_at"] = datetime.now(tz=UTC)
                new = r.model_copy(update=updates)
                self._runs[i] = new
                return new
        return None

    async def list_recent(self) -> list[IngestionRun]:
        async with self._lock:
            return list(self._runs)

    def __len__(self) -> int:
        return len(self._runs)

    def __iter__(self) -> Iterator[IngestionRun]:
        return iter(list(self._runs))
