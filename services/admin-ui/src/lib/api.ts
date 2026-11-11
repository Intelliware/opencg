// Pipeline-service client used by server components and a handful of client
// actions. Shared types live in @opencg/shared.

import type {
  ConnectorStatus,
  Entity,
  EntityListItem,
  EntityListResponse,
  IngestionRun,
  ConceptDetail,
  ConceptListItem,
  RelationshipEdge,
  RelationshipType,
  TraverseResponse,
  VectorSearchResponse,
} from "@opencg/shared";

const PIPELINE_URL =
  process.env.OPENCG__PIPELINE__URL || "http://pipeline:8000";

const NO_STORE: RequestInit = { cache: "no-store" };

export interface AuditRow {
  id: number;
  created_at: string;
  correlation_id: string;
  tenant: string;
  principal: string;
  roles: string[];
  tool: string;
  query: string;
  final_entity_ids: string[];
  candidate_ids: string[];
  final_context_hash: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  outcome: "ok" | "error";
  error_code?: string | null;
}

// --- Audits ----------------------------------------------------------------

export async function listRecentAudits(limit = 50): Promise<AuditRow[]> {
  const res = await fetch(`${PIPELINE_URL}/audit/recent?limit=${limit}`, NO_STORE);
  if (!res.ok) return [];
  const body = (await res.json()) as { items: AuditRow[] };
  return body.items ?? [];
}

export async function getAudit(id: number): Promise<AuditRow | null> {
  const res = await fetch(`${PIPELINE_URL}/audit/${id}`, NO_STORE);
  if (!res.ok) return null;
  return (await res.json()) as AuditRow;
}

// --- Pipeline readyz (status header on the vector page) -------------------

export interface ReadyzInfo {
  status: string;
  tenant?: string;
  embedding_model?: string;
  vector_size?: number;
}

export async function getReadyz(): Promise<ReadyzInfo | null> {
  try {
    const res = await fetch(`${PIPELINE_URL}/readyz`, NO_STORE);
    if (!res.ok) return null;
    return (await res.json()) as ReadyzInfo;
  } catch {
    return null;
  }
}

// --- Entities --------------------------------------------------------------

export interface ListEntitiesParams {
  source?: string;
  classification?: string;
  freshness_state?: string;
  limit?: number;
  offset?: number;
}

export async function listEntities(
  params: ListEntitiesParams = {},
): Promise<EntityListResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const res = await fetch(`${PIPELINE_URL}/entities?${qs}`, NO_STORE);
  if (!res.ok) {
    return { items: [] as EntityListItem[], total: 0, limit: params.limit ?? 50, offset: params.offset ?? 0 };
  }
  return (await res.json()) as EntityListResponse;
}

export async function getEntity(entityId: string): Promise<Entity | null> {
  const res = await fetch(`${PIPELINE_URL}/entities/${entityId}`, NO_STORE);
  if (!res.ok) return null;
  return (await res.json()) as Entity;
}

export async function tombstoneEntity(entityId: string): Promise<EntityListItem | null> {
  const res = await fetch(`${PIPELINE_URL}/entities/${entityId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as EntityListItem;
}

// --- Vector search ---------------------------------------------------------

export interface VectorSearchInput {
  query: string;
  top_k?: number;
  filters?: Record<string, unknown>;
}

export async function vectorSearch(
  input: VectorSearchInput,
): Promise<VectorSearchResponse | null> {
  const res = await fetch(`${PIPELINE_URL}/search/vector`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as VectorSearchResponse;
}

// --- Ingestion (via pipeline proxy) ----------------------------------------

export async function listConnectors(): Promise<ConnectorStatus[]> {
  const res = await fetch(`${PIPELINE_URL}/ingestion/connectors`, NO_STORE);
  if (!res.ok) return [];
  return (await res.json()) as ConnectorStatus[];
}

export async function listRecentRuns(): Promise<IngestionRun[]> {
  const res = await fetch(`${PIPELINE_URL}/ingestion/runs/recent`, NO_STORE);
  if (!res.ok) return [];
  return (await res.json()) as IngestionRun[];
}

export type RunGitResult =
  | { ok: true; run: IngestionRun }
  | { ok: false; status: number; message: string };

// The ingestion service validates repository URLs (scheme, host, local roots)
// and explains rejections; surface that message instead of a bare status.
export async function runGit(repoUrl: string): Promise<RunGitResult> {
  let res: Response;
  try {
    res = await fetch(`${PIPELINE_URL}/ingestion/git/run`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ repo_url: repoUrl }),
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 502, message: "Pipeline is unreachable." };
  }
  if (res.ok) return { ok: true, run: (await res.json()) as IngestionRun };
  let message = `Run failed (${res.status})`;
  try {
    const body = (await res.json()) as { detail?: { message?: string; detail?: { message?: string } } };
    // Pipeline forwards ingestion 4xx as {detail: <ingestion body>}.
    message = body.detail?.detail?.message ?? body.detail?.message ?? message;
  } catch {
    // Non-JSON error body: keep the status-only message.
  }
  return { ok: false, status: res.status >= 500 ? 502 : res.status, message };
}

// --- Knowledge graph ------------------------------------------------------

export async function listGraphConcepts(params: {
  state?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ items: ConceptListItem[]; total: number }> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, String(value));
  }
  const res = await fetch(`${PIPELINE_URL}/graph/concepts?${qs}`, NO_STORE);
  if (!res.ok) return { items: [], total: 0 };
  return (await res.json()) as { items: ConceptListItem[]; total: number };
}

export async function getGraphConcept(id: string): Promise<ConceptDetail | null> {
  const res = await fetch(`${PIPELINE_URL}/graph/concepts/${id}`, NO_STORE);
  if (!res.ok) return null;
  return (await res.json()) as ConceptDetail;
}

export interface GraphEdgeItem extends RelationshipEdge {
  evidence_entity_ids?: string[];
}

export async function listGraphEdges(params: {
  state?: string;
  type?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ items: GraphEdgeItem[]; total: number }> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, String(value));
  }
  const res = await fetch(`${PIPELINE_URL}/graph/edges?${qs}`, NO_STORE);
  if (!res.ok) return { items: [], total: 0 };
  return (await res.json()) as { items: GraphEdgeItem[]; total: number };
}

export interface TraverseParams {
  conceptId: string;
  depth?: number;
  types?: string;
  includeCandidates?: boolean;
  limit?: number;
}

export function traverseQuery(params: TraverseParams): string {
  const qs = new URLSearchParams({ concept_id: params.conceptId });
  if (params.depth !== undefined) qs.set("depth", String(params.depth));
  if (params.types) qs.set("types", params.types);
  if (params.includeCandidates) qs.set("include_candidates", "true");
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  return qs.toString();
}

export async function traverseGraph(params: TraverseParams): Promise<TraverseResponse> {
  const res = await fetch(`${PIPELINE_URL}/graph/traverse?${traverseQuery(params)}`, NO_STORE);
  if (!res.ok) return { nodes: [], edges: [] };
  return (await res.json()) as TraverseResponse;
}

export async function listGraphVocabulary(): Promise<RelationshipType[]> {
  const res = await fetch(`${PIPELINE_URL}/graph/vocab`, NO_STORE);
  if (!res.ok) return [];
  const body = (await res.json()) as { items: RelationshipType[] };
  return body.items;
}
