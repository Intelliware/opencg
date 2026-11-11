-- Audit log for state transitions on graph artifacts (concepts, edges,
-- vocabulary). Append-only with the same row-level immutability as
-- opencg.audit_log: a trigger blocks DELETE entirely and blocks UPDATE
-- on every column.
--
-- Required for the admin review workflow in `add-knowledge-graph`. Lives in
-- a separate init script so `040_graph.sql` (from `adopt-graphifyy`) stays
-- focused on storage shape and we can rollback this layer independently
-- if the review workflow ever needs reshaping.

CREATE TABLE opencg.graph_audit_log (
  id          BIGSERIAL PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor       TEXT NOT NULL,
  tenant      TEXT NOT NULL,
  target_kind TEXT NOT NULL CHECK (target_kind IN ('concept','edge','vocab')),
  target_id   TEXT NOT NULL,
  from_state  TEXT,
  to_state    TEXT,
  reason      TEXT,
  before      JSONB,
  after       JSONB
);

CREATE INDEX graph_audit_log_target_ix
  ON opencg.graph_audit_log (target_id, created_at DESC);
CREATE INDEX graph_audit_log_actor_ix
  ON opencg.graph_audit_log (actor, created_at DESC);
CREATE INDEX graph_audit_log_tenant_ix
  ON opencg.graph_audit_log (tenant, created_at DESC);

-- Immutability: forbid UPDATE and DELETE on every column. No legal_hold
-- escape hatch here (mirrors the discipline of audit_log; if we need one
-- later it lands in a follow-up).
CREATE OR REPLACE FUNCTION opencg.graph_audit_log_immutable()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'graph_audit_log: DELETE forbidden';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'graph_audit_log: UPDATE forbidden';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER graph_audit_log_no_modify
BEFORE UPDATE OR DELETE ON opencg.graph_audit_log
FOR EACH ROW EXECUTE FUNCTION opencg.graph_audit_log_immutable();

-- Apache AGE label types for the knowledge graph. We use AGE's openCypher
-- only as a queryable index over the same edges; the source of truth lives
-- in opencg.relationship_edge. Bootstrapping the labels here lets the
-- traversal endpoint issue Cypher without first checking-and-creating.
--
-- One Concept node label; one edge label per vocabulary entry. The label
-- names mirror the vocab `name` column verbatim.
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

DO $$
DECLARE
  v_name TEXT;
BEGIN
  -- Vertex label
  IF NOT EXISTS (
    SELECT 1 FROM ag_label
    WHERE name = 'Concept' AND graph = (SELECT graphid FROM ag_graph WHERE name = 'opencg')
  ) THEN
    PERFORM ag_catalog.create_vlabel(
      'opencg'::cstring,
      'Concept'::cstring
    );
  END IF;

  -- Edge labels (one per vocabulary entry)
  FOR v_name IN SELECT name FROM opencg.relationship_vocab LOOP
    IF NOT EXISTS (
      SELECT 1 FROM ag_label
      WHERE name = v_name AND graph = (SELECT graphid FROM ag_graph WHERE name = 'opencg')
    ) THEN
      PERFORM ag_catalog.create_elabel(
        'opencg'::cstring,
        v_name::cstring
      );
    END IF;
  END LOOP;
END
$$;

-- Grants for the application user.
GRANT SELECT, INSERT ON opencg.graph_audit_log TO CURRENT_USER;
GRANT USAGE, SELECT ON opencg.graph_audit_log_id_seq TO CURRENT_USER;
