"""The installed graphifyy version, stamped onto everything it produced.

`graphify` exposes no `__version__` attribute, so the
`getattr(graphify, "__version__", "0.0.0")` this replaces was silently in
effect everywhere: every chunk, concept, edge and evidence row recorded
`graphifyy/0.0.0`. The knowledge-graph spec requires the real distribution
version, and graphifyy is pinned `>=0.8,<0.9`, so a symbol-affecting patch
bump lands inside the pin — a frozen placeholder would defeat any
invalidation keyed on this string.

Resolution therefore goes through distribution metadata, and
`PackageNotFoundError` is left to propagate. A fallback here is the failure
this module exists to remove.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import version

_DISTRIBUTION = "graphifyy"


@lru_cache(maxsize=1)
def graphifyy_extractor_version() -> str:
    """`graphifyy/{version}`, e.g. `graphifyy/0.8.38`.

    Cached because the chunker stamps it onto every chunk's metadata and a
    distribution lookup walks the import path on each call.
    """
    return f"{_DISTRIBUTION}/{version(_DISTRIBUTION)}"
