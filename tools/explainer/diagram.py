"""Layout data for the system-overview diagram.

Kept as data rather than hand-written SVG markup so moving a box is a one-line
edit and the renderer stays generic. `app.js` turns this into SVG at load time,
computing edge paths from the box geometry.

Layout is a grid: the ingest chain across the top with the ontology parked at
its right-hand end, the two stores plus the graph on the second row, retrieval
and audit in the middle, consumers at the bottom, and the two cross-cutting
concerns boxed off on the right because they touch everything and drawing that
as edges would be unreadable.

Coordinates are in a 1040 x 560 viewBox. `pillar` links a node to a pillar page;
nodes without one (the source repo, the AI client) are not clickable.
"""

from __future__ import annotations

NODE_WIDTH = 148
NODE_HEIGHT = 56

ROW_INGEST = 36
ROW_STORE = 175
ROW_RETRIEVE = 316
ROW_CONSUME = 452

# kind: pillar | store | external
NODES: list[dict] = [
    # Ingest chain, left to right. Column gaps are wide enough that an edge
    # label fits between two boxes without touching either.
    {"id": "repo", "label": "Git repository", "sub": "the only source today",
     "x": 24, "y": ROW_INGEST, "kind": "external"},
    {"id": "ingestion", "label": "Ingestion", "sub": "clone, walk, filter",
     "x": 232, "y": ROW_INGEST, "kind": "pillar", "pillar": "ingestion"},
    {"id": "chunking", "label": "Chunking", "sub": "prose vs symbols",
     "x": 440, "y": ROW_INGEST, "kind": "pillar", "pillar": "chunking"},
    {"id": "model-providers", "label": "Model Providers", "sub": "embed + chat",
     "x": 648, "y": ROW_INGEST, "kind": "pillar", "pillar": "model-providers"},

    # Sits above the graph it would constrain rather than in the chain, because
    # it is a schema the chain consults, not a step the content passes through.
    {"id": "ontology", "label": "Ontology", "sub": "specified, not built",
     "x": 872, "y": ROW_INGEST, "kind": "pillar", "pillar": "ontology"},

    # Where ingested content lands.
    {"id": "catalog-store", "label": "Catalog Store", "sub": "Postgres, the truth",
     "x": 232, "y": ROW_STORE, "kind": "store", "pillar": "catalog-store"},
    {"id": "vector-index", "label": "Vector Index", "sub": "Qdrant, 768-dim",
     "x": 440, "y": ROW_STORE, "kind": "store", "pillar": "vector-index"},
    {"id": "knowledge-graph", "label": "Knowledge Graph", "sub": "concepts + edges",
     "x": 648, "y": ROW_STORE, "kind": "pillar", "pillar": "knowledge-graph"},

    # Query time.
    {"id": "admin-ui", "label": "Admin UI", "sub": "7 pages",
     "x": 24, "y": ROW_RETRIEVE, "kind": "pillar", "pillar": "admin-ui"},
    {"id": "retrieval-pipeline", "label": "Retrieval Pipeline", "sub": "fuse, police, budget",
     "x": 336, "y": ROW_RETRIEVE, "kind": "pillar", "pillar": "retrieval-pipeline"},
    {"id": "entitlement-audit", "label": "Audit Log", "sub": "append-only",
     "x": 604, "y": ROW_RETRIEVE, "kind": "store", "pillar": "entitlement-audit"},

    {"id": "client", "label": "Cursor / Claude", "sub": "any MCP client",
     "x": 88, "y": ROW_CONSUME, "kind": "external"},
    {"id": "mcp-server", "label": "MCP Server", "sub": "2 live tools",
     "x": 336, "y": ROW_CONSUME, "kind": "pillar", "pillar": "mcp-server"},

    # Cross-cutting: deliberately unconnected, see GROUPS below.
    {"id": "observability", "label": "Observability", "sub": "traces + tokens",
     "x": 872, "y": ROW_STORE, "kind": "pillar", "pillar": "observability"},
    {"id": "deployment", "label": "Deployment", "sub": "10 containers",
     "x": 872, "y": ROW_RETRIEVE, "kind": "pillar", "pillar": "deployment"},
]

# `dashed` marks a path that exists but is not part of the main request flow.
EDGES: list[dict] = [
    {"from": "repo", "to": "ingestion", "label": "clone"},
    {"from": "ingestion", "to": "chunking", "label": "files"},
    {"from": "chunking", "to": "model-providers", "label": "chunks"},
    {"from": "chunking", "to": "catalog-store", "label": "rows"},
    {"from": "model-providers", "to": "vector-index", "label": "vectors"},
    {"from": "model-providers", "to": "knowledge-graph", "label": "extract"},
    {"from": "ontology", "to": "knowledge-graph", "label": "no classes yet",
     "dashed": True},
    {"from": "catalog-store", "to": "retrieval-pipeline", "label": "lexical"},
    {"from": "vector-index", "to": "retrieval-pipeline", "label": "dense"},
    {"from": "knowledge-graph", "to": "retrieval-pipeline", "label": "not wired up yet",
     "dashed": True},
    {"from": "retrieval-pipeline", "to": "entitlement-audit", "label": "1 row / query"},
    {"from": "client", "to": "mcp-server", "label": "MCP"},
    {"from": "mcp-server", "to": "retrieval-pipeline", "label": "retrieve"},
    {"from": "admin-ui", "to": "retrieval-pipeline", "label": "admin API"},
]

# Faint containers drawn behind the nodes.
GROUPS: list[dict] = [
    {
        "label": "cross-cutting — touches every service",
        "x": 852,
        "y": ROW_STORE - 34,
        "width": NODE_WIDTH + 40,
        "height": (ROW_RETRIEVE + NODE_HEIGHT) - (ROW_STORE - 34) + 20,
    },
]


def as_dict() -> dict:
    return {
        "width": 1064,
        "height": ROW_CONSUME + NODE_HEIGHT + 24,
        "node_width": NODE_WIDTH,
        "node_height": NODE_HEIGHT,
        "nodes": NODES,
        "edges": EDGES,
        "groups": GROUPS,
        "note": "Solid edges are the main path content takes in and answers take out. "
                "The dashed edges are the two that do not exist yet: the knowledge graph "
                "is queried deliberately through its own API and does not influence "
                "normal retrieval, and the ontology that would say what kind of thing "
                "each concept is has been specified but not built.",
    }
