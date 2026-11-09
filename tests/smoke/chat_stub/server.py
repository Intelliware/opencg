#!/usr/bin/env python3
"""Deterministic Ollama-compatible chat endpoint for the full smoke test."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_lock = threading.Lock()
_stats = {"requests": 0}


def build_content(user_text: str) -> str:
    match = re.search(r"Smoke run:\s*([A-Za-z0-9_-]+)", user_text)
    run_id = match.group(1) if match else "unknown"
    catalogue = f"Smoke catalogue {run_id}"
    context = f"Context windows {run_id}"
    return json.dumps(
        {
            "concepts": [
                {
                    "name": catalogue,
                    "description": "Private knowledge selected for an AI tool.",
                    "aliases": [],
                },
                {
                    "name": context,
                    "description": "The bounded context supplied to a model.",
                    "aliases": [],
                },
            ],
            "relations": [
                {
                    "from": catalogue,
                    "relation": "related_to",
                    "to": context,
                    "evidence_span": "The openCG catalogue is related to context windows.",
                    "confidence": 0.99,
                },
                # A second candidate, so the e2e suite can promote one and
                # reject the other; smoke promotes the higher-confidence one.
                {
                    "from": context,
                    "relation": "derived_from",
                    "to": catalogue,
                    "evidence_span": "retrieval supplies only the evidence needed",
                    "confidence": 0.9,
                },
            ],
        }
    )


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/stats":
            with _lock:
                count = _stats["requests"]
            self._json(200, {"chat_requests": count})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        messages = request.get("messages") or []
        user_text = next(
            (
                message.get("content", "")
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        )
        with _lock:
            _stats["requests"] += 1
        self._json(
            200,
            {
                "model": request.get("model", "smoke-chat"),
                "message": {"role": "assistant", "content": build_content(user_text)},
                "done": True,
                "prompt_eval_count": 17,
                "eval_count": 11,
            },
        )

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 11434), Handler).serve_forever()
