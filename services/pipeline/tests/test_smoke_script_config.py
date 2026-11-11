from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "tests/smoke/run.sh"


def _describe(mode: str) -> str:
    env = {
        **os.environ,
        "SMOKE_DRY_RUN": "1",
        "SMOKE_CHAT_MODE": mode,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_default_smoke_mode_cannot_select_external_chat():
    output = _describe("stub")

    assert "external_chat=false" in output
    assert "max_documents=10" in output
    assert "max_chunks=20" in output


def test_cloud_canary_is_strictly_bounded():
    output = _describe("cloud")

    assert "external_chat=true" in output
    assert "max_documents=1" in output
    assert "max_chunks=2" in output
