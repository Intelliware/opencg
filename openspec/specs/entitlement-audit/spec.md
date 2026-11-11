# entitlement-audit Specification

## Purpose

Record every knowledge-graph state change (concept and relationship promotions, demotions, edits, merges and tombstones) in an append-only audit log, so each review decision stays attributable and inspectable.

## Requirements
### Requirement: Graph audit log

A new append-only table `opencg.graph_audit_log` SHALL capture every state transition on graph artifacts (`concept`, `edge`, `vocab`). It MUST share the same immutability semantics as `opencg.audit_log`: a row-level trigger MUST forbid `DELETE` and forbid `UPDATE` on every column.

Required columns: `id BIGSERIAL`, `created_at TIMESTAMPTZ`, `actor TEXT`, `tenant TEXT`, `target_kind TEXT CHECK (target_kind IN ('concept','edge','vocab'))`, `target_id TEXT`, `from_state TEXT`, `to_state TEXT`, `reason TEXT`, `before JSONB`, `after JSONB`.

#### Scenario: Update forbidden

- **WHEN** any code path attempts to `UPDATE` a row in `graph_audit_log`
- **THEN** the database raises an error and the operation fails

#### Scenario: Delete forbidden

- **WHEN** any code path attempts to `DELETE` a row in `graph_audit_log`
- **THEN** the database raises an error and the operation fails

#### Scenario: Every state transition writes a row

- **WHEN** an admin API endpoint changes a `state` on any graph artifact
- **THEN** a `graph_audit_log` row is written in the same transaction
- **AND** the row contains `before` and `after` JSONB snapshots of the affected artifact
