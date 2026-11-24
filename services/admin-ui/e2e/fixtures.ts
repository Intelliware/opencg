// Shared test fixtures: the current run's identity and a pipeline API helper.
// Every assertion and mutation targets data whose source_uri starts with the
// run's prefix (or concepts named after the run), never "the first row".
import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";
import type {
  AuditRecord,
  ConceptDetail,
  ConceptListItem,
  EntityListItem,
  EntityListResponse,
  RelationshipEdge,
  RelationshipType,
  RetrievalResponse,
  VectorSearchResponse,
} from "@opencg/shared";

import { PIPELINE_URL, TEST_AUTH_MODE } from "./env";
import { ServiceToken } from "./idp";

export interface Run {
  /** Unique per suite run; stamped into the fixture README and concept names. */
  id: string;
  /** source_uri prefix of every entity the run ingested. */
  prefix: string;
  /** Second fixture copy, ingested through the UI by ingestion.spec.ts. */
  uiRunId: string;
  uiFixtureDir: string;
}

function currentRun(): Run {
  const id = process.env.E2E_RUN_ID;
  const uiRunId = process.env.E2E_UI_RUN_ID;
  if (!id || !uiRunId) throw new Error("E2E_RUN_ID is unset; run the suite through playwright.config.ts");
  return {
    id,
    prefix: `git://opencg-smoke-${id}/`,
    uiRunId,
    uiFixtureDir: `/tmp/opencg-smoke-${uiRunId}`,
  };
}

export type CandidateEdge = RelationshipEdge & { evidence_entity_ids: string[] };

type Headers = Record<string, string>;

/**
 * Direct pipeline API calls. In oidc mode every call carries the service
 * account's token (opencg-smoke: admin, reader), never a user's session.
 */
export class Pipeline {
  constructor(
    private readonly api: APIRequestContext,
    private readonly token?: ServiceToken,
  ) {}

  private async auth(): Promise<{ headers: Headers }> {
    return { headers: this.token ? { authorization: `Bearer ${await this.token.get()}` } : {} };
  }

  private async get(url: string) {
    return this.api.get(url, await this.auth());
  }

  private async post(url: string, data: unknown) {
    return this.api.post(url, { ...(await this.auth()), data });
  }

  private async json<T>(res: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
    expect(res.ok(), `${res.url()} -> HTTP ${res.status()}`).toBe(true);
    return (await res.json()) as T;
  }

  async retrieve(correlationId: string, query: string): Promise<RetrievalResponse> {
    return this.json(
      await this.post("/retrieve", {
        correlation_id: correlationId,
        // Ignored in oidc mode: the pipeline derives identity from the token.
        identity: { principal: "local-dev", roles: ["admin", "reader"], tenant: "default" },
        tool: "retrieve_for_context",
        query,
        top_k: 10,
        token_budget: 2000,
      }),
    );
  }

  async auditFor(correlationId: string): Promise<AuditRecord> {
    const recent = await this.json<{ items: AuditRecord[] }>(await this.get("/audit/recent?limit=50"));
    const row = recent.items.find((item) => item.correlation_id === correlationId);
    expect(row, `audit row for ${correlationId}`).toBeTruthy();
    return this.json(await this.get(`/audit/${row!.id}`));
  }

  /** The run's entities (parents and chunks). The list is newest-first, so they lead it. */
  async runEntities(prefix: string): Promise<EntityListItem[]> {
    const page = await this.json<EntityListResponse>(await this.get("/entities?source=git&limit=200"));
    const items = page.items.filter((item) => item.source_uri.startsWith(prefix));
    expect(items.length, `entities under ${prefix}`).toBeGreaterThan(0);
    return items;
  }

  async entity(entityId: string): Promise<EntityListItem> {
    return this.json(await this.get(`/entities/${entityId}`));
  }

  async vectorSearch(query: string, filters?: Record<string, string>): Promise<VectorSearchResponse> {
    return this.json(await this.post("/search/vector", { query, top_k: 100, filters }));
  }

  /** The two concepts the chat stub names after the run. */
  async runConcepts(runId: string): Promise<{ catalogue: ConceptListItem; context: ConceptListItem }> {
    const found = await this.json<{ items: ConceptListItem[] }>(
      await this.get(`/graph/concepts?search=${encodeURIComponent(runId)}&limit=50`),
    );
    const named = (name: string) => found.items.find((item) => item.name === name);
    const catalogue = named(`Smoke catalogue ${runId}`);
    const context = named(`Context windows ${runId}`);
    expect(catalogue && context, `run concepts for ${runId}`).toBeTruthy();
    return { catalogue: catalogue!, context: context! };
  }

  async concept(conceptId: string): Promise<ConceptDetail> {
    return this.json(await this.get(`/graph/concepts/${conceptId}`));
  }

  async edges(state: "candidate" | "confirmed" | "tombstoned"): Promise<CandidateEdge[]> {
    const page = await this.json<{ items: CandidateEdge[] }>(
      await this.get(`/graph/edges?state=${state}&limit=200`),
    );
    return page.items;
  }

  /** Candidate edges between the run's two concepts. */
  async runCandidates(runId: string): Promise<CandidateEdge[]> {
    const { catalogue, context } = await this.runConcepts(runId);
    const ids = new Set([catalogue.concept_id, context.concept_id]);
    return (await this.edges("candidate")).filter(
      (edge) => ids.has(edge.from_concept_id) && ids.has(edge.to_concept_id),
    );
  }

  async vocabulary(): Promise<RelationshipType[]> {
    return (await this.json<{ items: RelationshipType[] }>(await this.get("/graph/vocab"))).items;
  }
}

export interface PageProblems {
  console: string[];
  requests: string[];
}

/** Collect uncaught errors, console errors and failed same-origin requests. */
export function watchPage(page: Page, origin: string): PageProblems {
  const problems: PageProblems = { console: [], requests: [] };
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.console.push(msg.text());
  });
  page.on("pageerror", (error) => problems.console.push(`uncaught: ${error.message}`));
  page.on("response", (res) => {
    if (res.url().startsWith(origin) && res.status() >= 400) {
      problems.requests.push(`${res.status()} ${res.request().method()} ${res.url()}`);
    }
  });
  page.on("requestfailed", (req) => {
    // Next cancels in-flight prefetches on navigation; that is not a failure.
    if (req.url().startsWith(origin) && req.failure()?.errorText !== "net::ERR_ABORTED") {
      problems.requests.push(`${req.failure()?.errorText} ${req.method()} ${req.url()}`);
    }
  });
  return problems;
}

export const test = base.extend<object, { run: Run; pipeline: Pipeline }>({
  run: [async ({}, use) => use(currentRun()), { scope: "worker" }],
  pipeline: [
    async ({ playwright }, use) => {
      const api = await playwright.request.newContext({ baseURL: PIPELINE_URL });
      await use(new Pipeline(api, TEST_AUTH_MODE === "oidc" ? new ServiceToken() : undefined));
      await api.dispose();
    },
    { scope: "worker" },
  ],
});

export { expect };
