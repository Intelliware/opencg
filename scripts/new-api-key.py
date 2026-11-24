#!/usr/bin/env python3
"""Generate a dev-only openCG API key (add-identity-and-opa, design D1a).

Prints the raw key ONCE and the JSON entry to add to the file named by
OPENCG__AUTH__API_KEYS_FILE. Only the SHA-256 of the key is ever stored.
API keys are accepted only when OPENCG__ENVIRONMENT=dev.

Usage: scripts/new-api-key.py NAME [PRINCIPAL] [ROLES]
       make api-key NAME=ci ROLES=reader
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys


def main(argv: list[str]) -> int:
    if not argv or not argv[0]:
        print(__doc__, file=sys.stderr)
        return 2
    name = argv[0]
    principal = argv[1] if len(argv) > 1 and argv[1] else f"apikey:{name}"
    roles = [r for r in (argv[2] if len(argv) > 2 else "reader").split(",") if r]
    raw = "ock_" + secrets.token_urlsafe(32)
    entry = {
        "name": name,
        "key_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "principal": principal,
        "roles": roles,
    }
    print("API key (shown once; store it in your client, not in git):", file=sys.stderr)
    print(raw)
    print("\nAdd this entry to the JSON list in OPENCG__AUTH__API_KEYS_FILE:", file=sys.stderr)
    print(json.dumps(entry), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
