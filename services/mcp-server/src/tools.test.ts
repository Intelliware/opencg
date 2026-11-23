import { describe, expect, it } from "vitest";
import {
  ConceptNotFoundError,
  NotImplementedInMvpError,
  TOOL_DEFINITIONS,
  callTool,
} from "./tools.js";
import { loadConfig } from "./config.js";
import type { PipelineClient } from "./pipeline-client.js";
import { PipelineRequestError } from "./pipeline-client.js";

const config = loadConfig({
  OPENCG__IDENTITY__PRINCIPAL: "alice",
  OPENCG__IDENTITY__ROLES: "reader",
  OPENCG__PIPELINE__URL: "http://unused",
});

class FakePipeline {
  public lastRequest: any = null;
  public traverseError: Error | null = null;
  async retrieve(req: any) {
    this.lastRequest = req;
    return {
      correlation_id: req.correlation_id,
      fragments: [],
      usage: { total_tokens_in: 0, total_tokens_out: 0, total_latency_ms: 1, by_stage: [] },
      final_context_hash: "deadbeef",
    };
  }
  async health() {
    return true;
  }
  async traverse(req: any) {
    this.lastRequest = req;
    if (this.traverseError) throw this.traverseError;
    return {
      nodes: [{ concept_id: req.concept_id, name: "Start" }],
      edges: [],
    };
  }
}

describe("tools/list", () => {
  it("includes all five v0 tools, all under opencg/ namespace", () => {
    const names = TOOL_DEFINITIONS.map((t) => t.name);
    expect(names).toContain("opencg/retrieve_for_context");
    expect(names).toContain("opencg/search");
    expect(names).toContain("opencg/get_entity");
    expect(names).toContain("opencg/traverse_graph");
    expect(names).toContain("opencg/submit_feedback");
    for (const t of TOOL_DEFINITIONS) {
      expect(t.name.startsWith("opencg/")).toBe(true);
      expect(t.inputSchema).toBeTypeOf("object");
    }
  });
});

describe("retrieve_for_context", () => {
  it("propagates identity and generates a correlation id when none supplied", async () => {
    const pipeline = new FakePipeline() as unknown as PipelineClient;
    const result = await callTool(
      "opencg/retrieve_for_context",
      { query: "hello" },
      { config, pipeline },
    );
    const sent = (pipeline as any).lastRequest;
    expect(sent.identity.principal).toBe("alice");
    expect(sent.identity.tenant).toBe("default");
    expect(sent.identity.roles).toEqual(["reader"]);
    expect(sent.correlation_id).toBeTypeOf("string");
    expect((result as any).correlation_id).toEqual(sent.correlation_id);
  });

  it("preserves a caller-supplied correlation id", async () => {
    const pipeline = new FakePipeline() as unknown as PipelineClient;
    await callTool(
      "opencg/retrieve_for_context",
      { query: "hello" },
      { config, pipeline, correlationId: "cid-123" },
    );
    expect((pipeline as any).lastRequest.correlation_id).toBe("cid-123");
  });

  it("rejects empty queries", async () => {
    const pipeline = new FakePipeline() as unknown as PipelineClient;
    await expect(
      callTool("opencg/retrieve_for_context", { query: " " }, { config, pipeline }),
    ).rejects.toThrow(/required/);
  });
});

describe("stub tools", () => {
  it.each([
    "opencg/search",
    "opencg/get_entity",
    "opencg/submit_feedback",
  ])("%s throws NotImplementedInMvpError", async (name) => {
    const pipeline = new FakePipeline() as unknown as PipelineClient;
    await expect(callTool(name, {}, { config, pipeline })).rejects.toBeInstanceOf(
      NotImplementedInMvpError,
    );
  });
});

describe("traverse_graph", () => {
  it("forwards traversal arguments and returns the pipeline payload", async () => {
    const pipeline = new FakePipeline() as unknown as PipelineClient;
    const result = await callTool(
      "opencg/traverse_graph",
      {
        concept_id: "c1",
        types: ["depends_on"],
        depth: 3,
        limit: 25,
        include_candidates: true,
      },
      { config, pipeline },
    );

    expect((pipeline as any).lastRequest).toEqual({
      concept_id: "c1",
      types: ["depends_on"],
      depth: 3,
      limit: 25,
      include_candidates: true,
    });
    expect((result as any).nodes[0].concept_id).toBe("c1");
  });

  it("maps a pipeline 404 to concept_not_found", async () => {
    const fake = new FakePipeline();
    fake.traverseError = new PipelineRequestError(404, '{"detail":"not found"}');
    const pipeline = fake as unknown as PipelineClient;

    await expect(
      callTool(
        "opencg/traverse_graph",
        { concept_id: "missing" },
        { config, pipeline },
      ),
    ).rejects.toBeInstanceOf(ConceptNotFoundError);
  });

  it("rejects a missing concept id", async () => {
    const pipeline = new FakePipeline() as unknown as PipelineClient;
    await expect(
      callTool("opencg/traverse_graph", {}, { config, pipeline }),
    ).rejects.toThrow(/concept_id/);
  });
});
