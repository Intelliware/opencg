// Wire types shared between MCP server and admin UI. Pydantic mirrors in
// packages/shared-py/opencg_shared/types.py — keep in sync.

export interface IdentityContext {
  principal: string;
  roles: readonly string[];
  tenant: string;
}

export interface RetrievalRequest {
  correlation_id: string;
  identity: IdentityContext;
  tool: string;
  query: string;
  top_k?: number;
  token_budget?: number;
  filters?: Record<string, unknown>;
}

export interface ContextFragment {
  entity_id: string;
  source: string;
  source_uri: string;
  title?: string;
  text: string;
  score: number;
  tokens: number;
  classification: string;
}

export interface StageUsage {
  stage: string;
  model?: string;
  provider?: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  /** Estimated USD cost; null when unpriced or the stage made no model call. */
  cost_usd?: number | null;
}

/** Usage for one (provider, model) pair. `cost_usd: null` means unpriced, never free. */
export interface ProviderUsage {
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number | null;
}

export interface UsageEnvelope {
  total_tokens_in: number;
  total_tokens_out: number;
  total_latency_ms: number;
  by_stage: readonly StageUsage[];
  by_provider?: readonly ProviderUsage[];
  /** Sum of the priced entries in `by_provider`. */
  estimated_cost_usd?: number;
  /** False when any `by_provider` entry is unpriced. */
  cost_complete?: boolean;
}

export interface RetrievalResponse {
  correlation_id: string;
  fragments: readonly ContextFragment[];
  usage: UsageEnvelope;
  final_context_hash: string;
  vector_collection?: string;
  vector_snapshot_id?: string;
}

export interface AuditRecord {
  id: number;
  created_at: string;
  correlation_id: string;
  tenant: string;
  principal: string;
  roles: readonly string[];
  tool: string;
  query: string;
  candidate_ids: readonly string[];
  final_entity_ids: readonly string[];
  final_context_hash: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  outcome: "ok" | "error";
  error_code?: string;
  /** Null on rows written before cost was recorded. */
  estimated_cost_usd?: number | null;
  usage_by_provider?: readonly ProviderUsage[] | null;
}

export interface IngestEvent {
  type: "document_created" | "document_updated" | "document_tombstoned";
  tenant: string;
  entity_id: string;
  source: string;
  source_uri: string;
  content_hash: string;
}

// --- Admin: catalog read ---------------------------------------------------

export interface EntityListItem {
  entity_id: string;
  tenant: string;
  source: string;
  source_uri: string;
  title?: string | null;
  classification: string;
  freshness_state: string;
  updated_at: string;
  tombstoned_at?: string | null;
}

export interface EntityRef {
  entity_id: string;
  title?: string | null;
  source_uri: string;
}

export interface EntityLineage {
  parent?: EntityRef | null;
  children: readonly EntityRef[];
}

export interface EntityAuditAppearance {
  id: number;
  created_at: string;
  correlation_id: string;
  tool: string;
  query: string;
  outcome: "ok" | "error";
}

export interface Entity extends EntityListItem {
  body: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  source_revision?: string | null;
  parent_entity_id?: string | null;
  created_at: string;
  ingested_at: string;
  last_verified_at: string;
  lineage: EntityLineage;
  audit_appearances: readonly EntityAuditAppearance[];
}

export interface EntityListResponse {
  items: readonly EntityListItem[];
  total: number;
  limit: number;
  offset: number;
}

// --- Admin: vector search --------------------------------------------------

export interface VectorSearchHit {
  entity_id: string;
  score: number;
  source: string;
  source_uri: string;
  title?: string | null;
  classification: string;
  snippet: string;
  collection?: string;
}

export interface VectorSearchResponse {
  hits: readonly VectorSearchHit[];
  model: string;
  provider: string;
  tokens_in: number;
  /** Estimated USD cost of the query embedding; null when unpriced. */
  cost_usd?: number | null;
  usage?: UsageEnvelope;
}

// --- Admin: ingestion ------------------------------------------------------

export interface ConnectorStatus {
  name: string;
  supported: boolean;
  reason?: string;
}

export type IngestionRunStatus = "queued" | "running" | "succeeded" | "failed";

export interface IngestionRun {
  run_id: string;
  connector: string;
  repo?: string;
  started_at: string;
  finished_at?: string | null;
  status: IngestionRunStatus;
  parents?: number;
  chunks?: number;
  error?: string | null;
}

// --- Knowledge graph -------------------------------------------------------

export type EdgeState = "candidate" | "confirmed" | "tombstoned";

export interface RelationshipType {
  name: string;
  description: string;
  inverse?: string | null;
  directed: boolean;
  deprecated_at?: string | null;
}

export interface ConceptListItem {
  concept_id: string;
  tenant: string;
  name: string;
  state: EdgeState;
  confidence?: number | null;
  aliases: readonly string[];
  symbol_id?: string | null;
  symbol_kind?: string | null;
  updated_at: string;
  tombstoned_at?: string | null;
}

export interface Concept extends ConceptListItem {
  dedupe_key: string;
  description?: string | null;
  extractor_version?: string | null;
  source_entity_id?: string | null;
  created_at: string;
}

export interface RelationshipEdge {
  edge_id: string;
  tenant: string;
  type: string;
  from_concept_id: string;
  to_concept_id: string;
  state: EdgeState;
  confidence: number;
  extractor_version?: string | null;
  created_at: string;
  updated_at: string;
  tombstoned_at?: string | null;
}

export interface Neighbour {
  edge: RelationshipEdge;
  peer: ConceptListItem;
  evidence_entity_ids: readonly string[];
}

export interface ConceptDetail extends Concept {
  neighbours_confirmed: readonly Neighbour[];
  neighbours_candidate: readonly Neighbour[];
}

export interface TraverseRequest {
  concept_id: string;
  types?: readonly string[] | null;
  depth?: number;
  limit?: number;
  include_candidates?: boolean;
}

export interface TraverseResponse {
  nodes: readonly ConceptListItem[];
  edges: readonly RelationshipEdge[];
}

export interface ExtractedConcept {
  name: string;
  description?: string | null;
  aliases?: readonly string[];
}

export interface ExtractedRelation {
  from: string;
  relation: string;
  to: string;
  evidence_span?: string | null;
  confidence: number;
}

export interface ExtractionResult {
  concepts: readonly ExtractedConcept[];
  relations: readonly ExtractedRelation[];
}

export interface GraphAuditRow {
  id: number;
  created_at: string;
  actor: string;
  tenant: string;
  target_kind: "concept" | "edge" | "vocab";
  target_id: string;
  from_state?: string | null;
  to_state?: string | null;
  reason?: string | null;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
}
