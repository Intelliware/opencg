-- Estimated cost on retrieval audit rows (add-observability-stack, design D10).
-- Both columns are nullable: rows written before cost was recorded stay NULL
-- and the admin UI shows them as "—". Adding columns leaves the immutability
-- trigger (030_audit.sql) in force: it compares whole rows, so the new
-- columns are covered by it as well.
--
-- Idempotent, so an existing database can apply it by hand:
--   docker compose exec postgres psql -U opencg -d opencg \
--     -f /docker-entrypoint-initdb.d/060_audit_cost.sql

ALTER TABLE opencg.audit_log
  ADD COLUMN IF NOT EXISTS estimated_cost_usd NUMERIC(12,6),
  ADD COLUMN IF NOT EXISTS usage_by_provider  JSONB;
