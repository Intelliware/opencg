from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_stub_module():
    path = Path(__file__).parents[3] / "tests/smoke/chat_stub/server.py"
    spec = importlib.util.spec_from_file_location("smoke_chat_stub", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_chat_stub_returns_unique_schema_valid_relationships():
    module = _load_stub_module()

    content = json.loads(module.build_content("Smoke run: run-123"))

    assert [item["name"] for item in content["concepts"]] == [
        "Smoke catalogue run-123",
        "Context windows run-123",
    ]
    assert content["relations"] == [
        {
            "from": "Smoke catalogue run-123",
            "relation": "related_to",
            "to": "Context windows run-123",
            "evidence_span": "The openCG catalogue is related to context windows.",
            "confidence": 0.99,
        },
        {
            "from": "Context windows run-123",
            "relation": "derived_from",
            "to": "Smoke catalogue run-123",
            "evidence_span": "retrieval supplies only the evidence needed",
            "confidence": 0.9,
        },
    ]
