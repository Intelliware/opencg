-- Access audit log (add-identity-and-opa, design D10): one row for every
-- denied API action and every allowed state-changing one (entity.tombstone,
-- graph.write, vocab.write, ingestion.run), with the real actor and the OPA
-- policy package + revision that decided it. Allowed reads are not logged here
-- (retrievals are in opencg.audit_log); authentication failures go to logs and
-- metrics only.
--
-- Append-only like graph_audit_log: a trigger forbids UPDATE and DELETE.
--
-- RE-RUNNABLE. Init scripts only run when the Postgres volume is created, so on
-- an existing volume apply this file with
--   make db-apply SQL=070_access_audit.sql
-- Every statement is idempotent and the grants are repeated here because
-- 090_grants.sql does not run again on an existing volume.

CREATE TABLE IF NOT EXISTS opencg.access_audit_log (
  id               BIGSERIAL PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  correlation_id   TEXT,
  service          TEXT NOT NULL,
  principal        TEXT NOT NULL,
  roles            TEXT[] NOT NULL DEFAULT '{}',
  tenant           TEXT NOT NULL,
  auth_method      TEXT NOT NULL,
  action           TEXT NOT NULL,
  resource         TEXT,
  decision         TEXT NOT NULL CHECK (decision IN ('allow', 'deny')),
  reason           TEXT NOT NULL,
  policy_package   TEXT,
  policy_revision  TEXT
);

CREATE INDEX IF NOT EXISTS access_audit_log_principal_ix
  ON opencg.access_audit_log (principal, created_at DESC);
CREATE INDEX IF NOT EXISTS access_audit_log_action_ix
  ON opencg.access_audit_log (action, created_at DESC);
CREATE INDEX IF NOT EXISTS access_audit_log_correlation_ix
  ON opencg.access_audit_log (correlation_id);

CREATE OR REPLACE FUNCTION opencg.access_audit_log_immutable()
RETURNS TRIGGER AS $$
BEGIN
  -- Called for UPDATE, DELETE (row) and TRUNCATE (statement).
  RAISE EXCEPTION 'access_audit_log: % forbidden', TG_OP;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgname = 'access_audit_log_no_modify'
      AND tgrelid = 'opencg.access_audit_log'::regclass
  ) THEN
    CREATE TRIGGER access_audit_log_no_modify
    BEFORE UPDATE OR DELETE ON opencg.access_audit_log
    FOR EACH ROW EXECUTE FUNCTION opencg.access_audit_log_immutable();
  END IF;
END
$$;

-- TRUNCATE skips row triggers; forbid it too so the log cannot be emptied by
-- the application role.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgname = 'access_audit_log_no_truncate'
      AND tgrelid = 'opencg.access_audit_log'::regclass
  ) THEN
    CREATE TRIGGER access_audit_log_no_truncate
    BEFORE TRUNCATE ON opencg.access_audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION opencg.access_audit_log_immutable();
  END IF;
END
$$;

-- Retrieval audit: how the caller authenticated (oidc / none / api_key).
-- Nullable, so rows written before this change stay valid. The existing
-- audit_log immutability trigger covers the new column.
ALTER TABLE opencg.audit_log ADD COLUMN IF NOT EXISTS auth_method TEXT;

-- Grants, matching 050_graph_audit.sql / 090_grants.sql: the application role
-- (the one running init scripts and `make db-apply`) may read and append.
GRANT SELECT, INSERT ON opencg.access_audit_log TO CURRENT_USER;
GRANT USAGE, SELECT ON SEQUENCE opencg.access_audit_log_id_seq TO CURRENT_USER;
