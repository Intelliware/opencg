-- Knowledge graph storage. The minimal table set this change needs to land:
--
--   relationship_vocab    curated, extensible relationship types
--   concept                node table (one row per concept)
--   relationship_edge      typed directed edge between two concepts
--   relationship_evidence  cross-table linking edges to the source chunks
--                          they were extracted from
--
-- The full review-workflow audit trail (graph_audit_log) + AGE label types +
-- soft-delete triggers are introduced by openspec/changes/add-knowledge-graph
-- when it ships. This migration intentionally stops short of them — we only
-- need write-only storage in this change.

SET search_path = ag_catalog, "$user", public;

-- ---------------------------------------------------------------------------
-- Vocabulary
-- ---------------------------------------------------------------------------

CREATE TABLE opencg.relationship_vocab (
  name          TEXT PRIMARY KEY,
  description   TEXT NOT NULL,
  inverse       TEXT,
  directed      BOOLEAN NOT NULL DEFAULT TRUE,
  deprecated_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seven domain-of-discourse relations the LLM extractor produces plus three
-- code-structure relations graphifyy produces. Marker: edges whose source row
-- references a name not present here will fail at insert (FK).
INSERT INTO opencg.relationship_vocab (name, description, inverse, directed) VALUES
  ('depends_on',  'A requires B to function (semantic dependency, not necessarily a code call)', 'depended_on_by', TRUE),
  ('defined_in',  'A is declared inside B (concept membership; e.g., a function defined in a file)', 'defines', TRUE),
  ('supersedes',  'A replaces B (A is the newer version of the same concept)', 'superseded_by', TRUE),
  ('mentions',    'A references B by name without invoking or depending on it', 'mentioned_by', TRUE),
  ('related_to',  'A and B share a concept or category (symmetric)', 'related_to', FALSE),
  ('causes',      'A leads to B happening (causal)', 'caused_by', TRUE),
  ('derived_from','A is a derivative or extension of B', 'parent_of', TRUE),
  -- Code-structure relations from graphifyy (tree-sitter, deterministic):
  ('calls',       'Function A invokes function B (extracted from a call expression)', 'called_by', TRUE),
  ('imports',     'Module/file A imports symbol or module B', 'imported_by', TRUE),
  ('uses',        'A references B''s identifier without invoking it (read or pass-through)', 'used_by', TRUE);

-- ---------------------------------------------------------------------------
-- Concepts (nodes)
-- ---------------------------------------------------------------------------

CREATE TABLE opencg.concept (
  concept_id        UUID PRIMARY KEY,
  tenant            TEXT NOT NULL,
  name              TEXT NOT NULL,
  -- Normalised dedupe key: lower(unaccent(squeeze_whitespace(name))). Computed
  -- in application code (or via a generated column in a follow-up). The
  -- unique constraint below is the FK target for relationship endpoints.
  dedupe_key        TEXT NOT NULL,
  description       TEXT,
  aliases           TEXT[] NOT NULL DEFAULT '{}',
  state             TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN ('candidate','confirmed','tombstoned')),
  confidence        FLOAT,
  extractor_version TEXT,
  -- Code-specific: graphifyy's stable per-symbol id (e.g.
  -- module.path.ClassName.method_name). Optional; null for non-code concepts.
  symbol_id         TEXT,
  symbol_kind       TEXT,
  source_entity_id  UUID,  -- the catalog row this concept was first seen in
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  tombstoned_at     TIMESTAMPTZ
);

CREATE UNIQUE INDEX concept_dedupe_uq ON opencg.concept (tenant, dedupe_key);
CREATE INDEX concept_state_ix         ON opencg.concept (tenant, state);
CREATE INDEX concept_symbol_ix        ON opencg.concept (tenant, symbol_id) WHERE symbol_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Edges (typed relationships between concepts)
-- ---------------------------------------------------------------------------

CREATE TABLE opencg.relationship_edge (
  edge_id            UUID PRIMARY KEY,
  tenant             TEXT NOT NULL,
  type               TEXT NOT NULL REFERENCES opencg.relationship_vocab(name),
  from_concept_id    UUID NOT NULL REFERENCES opencg.concept(concept_id),
  to_concept_id      UUID NOT NULL REFERENCES opencg.concept(concept_id),
  state              TEXT NOT NULL DEFAULT 'candidate' CHECK (state IN ('candidate','confirmed','tombstoned')),
  confidence         FLOAT NOT NULL DEFAULT 0.0,
  extractor_version  TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  tombstoned_at      TIMESTAMPTZ
);

CREATE UNIQUE INDEX relationship_edge_triple_uq
  ON opencg.relationship_edge (tenant, from_concept_id, type, to_concept_id);
CREATE INDEX relationship_edge_state_confidence_ix
  ON opencg.relationship_edge (state, confidence DESC);
CREATE INDEX relationship_edge_from_ix ON opencg.relationship_edge (from_concept_id);
CREATE INDEX relationship_edge_to_ix   ON opencg.relationship_edge (to_concept_id);

-- ---------------------------------------------------------------------------
-- Evidence: which catalog chunk did each edge come from?
-- ---------------------------------------------------------------------------

CREATE TABLE opencg.relationship_evidence (
  evidence_id       BIGSERIAL PRIMARY KEY,
  edge_id           UUID NOT NULL REFERENCES opencg.relationship_edge(edge_id) ON DELETE CASCADE,
  entity_id         UUID NOT NULL REFERENCES opencg.entity(entity_id),
  span              TEXT,
  extractor_version TEXT,
  confidence        FLOAT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX relationship_evidence_edge_ix   ON opencg.relationship_evidence (edge_id);
CREATE INDEX relationship_evidence_entity_ix ON opencg.relationship_evidence (entity_id);

-- ---------------------------------------------------------------------------
-- Grants (the `opencg` role exists already from 090_grants.sql' s ALTER DEFAULT)
-- ---------------------------------------------------------------------------

GRANT SELECT, INSERT, UPDATE ON opencg.relationship_vocab    TO CURRENT_USER;
GRANT SELECT, INSERT, UPDATE ON opencg.concept               TO CURRENT_USER;
GRANT SELECT, INSERT, UPDATE ON opencg.relationship_edge     TO CURRENT_USER;
GRANT SELECT, INSERT, UPDATE ON opencg.relationship_evidence TO CURRENT_USER;
GRANT USAGE, SELECT ON opencg.relationship_evidence_evidence_id_seq TO CURRENT_USER;
