#!/usr/bin/env python3
"""Compute, check or write the OPA policy revision (design D7).

The revision is the SHA-256 of everything that decides an outcome:

* every ``policies/*.rego`` file except ``*_test.rego`` (tests don't change a
  decision), byte for byte;
* every ``data/*.json`` file, parsed and re-serialised canonically (sorted
  keys, compact separators), with ``meta.revision`` removed from
  ``data/opencg.json`` so the file can carry its own revision.

Each file contributes ``<relative path> NUL <content> NUL`` in path order.

    revision.py            print the computed revision
    revision.py --check    exit 1 if data/opencg.json's meta.revision is stale
    revision.py --write    store the computed revision in data/opencg.json

Standard library only, so `make opa-revision` / `make opa-test` need nothing
beyond python3.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "opencg.json"


def _canonical_json(path: Path) -> bytes:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if path == DATA_FILE:
        meta = dict(doc.get("meta", {}))
        meta.pop("revision", None)
        doc = {**doc, "meta": meta}
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def compute() -> str:
    files = [p for p in (ROOT / "policies").glob("*.rego") if not p.name.endswith("_test.rego")]
    files += list((ROOT / "data").glob("*.json"))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(ROOT).as_posix()):
        content = _canonical_json(path) if path.suffix == ".json" else path.read_bytes()
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def recorded() -> str | None:
    return json.loads(DATA_FILE.read_text(encoding="utf-8")).get("meta", {}).get("revision")


def write(revision: str) -> None:
    text = DATA_FILE.read_text(encoding="utf-8")
    new, n = re.subn(r'("revision"\s*:\s*)"[^"]*"', rf'\g<1>"{revision}"', text, count=1)
    if n != 1:
        sys.exit(f"{DATA_FILE}: no meta.revision field to update")
    DATA_FILE.write_text(new, encoding="utf-8")


def main(argv: list[str]) -> int:
    expected = compute()
    if argv == ["--check"]:
        actual = recorded()
        if actual != expected:
            print(
                f"infra/opa/data/opencg.json meta.revision is stale: recorded {actual!r}, "
                f"expected {expected!r}. Run `make opa-revision`.",
                file=sys.stderr,
            )
            return 1
        print(f"OPA policy revision {expected} is current")
        return 0
    if argv == ["--write"]:
        write(expected)
        print(f"OPA policy revision set to {expected}")
        return 0
    if not argv:
        print(expected)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
