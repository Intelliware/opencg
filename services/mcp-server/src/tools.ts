// MCP tool schemas + handlers for the thin MVP.
// Only `retrieve_for_context` is implemented end-to-end; the other tool stubs
// are registered (so `tools/list` returns the v0 surface) but throw a
// `not_implemented_in_mvp` error if called.

import { randomUUID } from "node:crypto";
import type {
  RetrievalRequest,
  RetrievalResponse,
  TraverseRequest,
  TraverseResponse,
} from "@opencg/shared";
import type { McpConfig } from "./config.js";
import { PipelineRequestError, type PipelineClient } from "./pipeline-client.js";

export type ToolName =
  | "search"
  | "retrieve_for_context"
  | "get_entity"
  | "traverse_graph"
  | "submit_feedback";

export interface ToolDefinition {
  name: `opencg/${ToolName}`;
  description: string;
  inputSchema: Record<string, unknown>;
}

export const TOOL_DEFINITIONS: ToolDefinition[] = [
  {
    name: "opencg/retrieve_for_context",
    description:
      "Retrieve context fragments from the knowledge catalogue for a natural language query. Returns ordered fragments fitting a token budget, plus per-stage usage telemetry and a correlation_id that links back to the immutable audit record.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Natural language query." },
        top_k: { type: "integer", minimum: 1, maximum: 200, default: 20 },
        token_budget: { type: "integer", minimum: 100, default: 4000 },
        filters: { type: "object", additionalProperties: true },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "opencg/search",
    description: "Lightweight search returning entity IDs + scores. (Not implemented in thin MVP.)",
    inputSchema: {
      type: "object",
      properties: { query: { type: "string" }, top_k: { type: "integer" } },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "opencg/get_entity",
    description: "Fetch a single entity by ID. (Not implemented in thin MVP.)",
    inputSchema: {
      type: "object",
      properties: { entity_id: { type: "string" } },
      required: ["entity_id"],
      additionalProperties: false,
    },
  },
  {
    name: "opencg/traverse_graph",
    description:
      "Traverse confirmed named relationships from a starting concept. Candidate edges are excluded unless include_candidates is true.",
    inputSchema: {
      type: "object",
      properties: {
        concept_id: { type: "string" },
        types: { type: "array", items: { type: "string" } },
        depth: { type: "integer", minimum: 1, maximum: 4, default: 2 },
        limit: { type: "integer", minimum: 1, maximum: 200, default: 50 },
        include_candidates: { type: "boolean", default: false },
      },
      required: ["concept_id"],
      additionalProperties: false,
    },
  },
  {
    name: "opencg/submit_feedback",
    description: "Submit usage feedback for a prior retrieval. (Not implemented in thin MVP.)",
    inputSchema: {
      type: "object",
      properties: {
        correlation_id: { type: "string" },
        rating: { type: "string", enum: ["useful", "partially_useful", "not_useful"] },
        notes: { type: "string" },
      },
      required: ["correlation_id", "rating"],
      additionalProperties: false,
    },
  },
];

export class NotImplementedInMvpError extends Error {
  code = "not_implemented_in_mvp" as const;
}

export class ConceptNotFoundError extends Error {
  code = "concept_not_found" as const;
}

/** Bad tool arguments: counted as `outcome="rejected"`. */
export class ToolValidationError extends Error {
  code = "invalid_arguments" as const;
}

export class UnknownToolError extends Error {
  code = "unknown_tool" as const;
}

/** `opencg/retrieve_for_context` → `retrieve_for_context`; anything unadvertised → `unknown`. */
export function toolLabel(name: string): string {
  return TOOL_DEFINITIONS.some((t) => t.name === name) ? name.replace(/^opencg\//, "") : "unknown";
}

export interface RetrieveContextArgs {
  query: string;
  top_k?: number;
  token_budget?: number;
  filters?: Record<string, unknown>;
}

export interface ToolCallContext {
  correlationId?: string;
  config: McpConfig;
  pipeline: PipelineClient;
}

export async function callTool(
  name: string,
  args: unknown,
  ctx: ToolCallContext,
): Promise<RetrievalResponse | TraverseResponse | Record<string, unknown>> {
  switch (name) {
    case "opencg/retrieve_for_context":
      return retrieveForContext(args as RetrieveContextArgs, ctx);
    case "opencg/traverse_graph":
      return traverseGraph(args as TraverseRequest, ctx);
    case "opencg/search":
    case "opencg/get_entity":
    case "opencg/submit_feedback":
      throw new NotImplementedInMvpError(`${name} ships in a follow-up change`);
    default:
      throw new UnknownToolError(`Unknown tool: ${name}`);
  }
}

async function traverseGraph(
  args: TraverseRequest,
  ctx: ToolCallContext,
): Promise<TraverseResponse> {
  if (!args || typeof args.concept_id !== "string" || !args.concept_id.trim()) {
    throw new ToolValidationError("concept_id is required and must be a non-empty string");
  }
  try {
    return await ctx.pipeline.traverse(
      {
        concept_id: args.concept_id,
        ...(args.types !== undefined ? { types: args.types } : {}),
        ...(args.depth !== undefined ? { depth: args.depth } : {}),
        ...(args.limit !== undefined ? { limit: args.limit } : {}),
        ...(args.include_candidates !== undefined
          ? { include_candidates: args.include_candidates }
          : {}),
      },
      ctx.correlationId,
    );
  } catch (error) {
    if (error instanceof PipelineRequestError && error.statusCode === 404) {
      throw new ConceptNotFoundError(`concept not found: ${args.concept_id}`);
    }
    throw error;
  }
}

async function retrieveForContext(
  args: RetrieveContextArgs,
  ctx: ToolCallContext,
): Promise<RetrievalResponse> {
  if (!args || typeof args.query !== "string" || !args.query.trim()) {
    throw new ToolValidationError("query is required and must be a non-empty string");
  }
  const correlation_id = ctx.correlationId || randomUUID();
  const req: RetrievalRequest = {
    correlation_id,
    identity: {
      principal: ctx.config.identity.principal,
      roles: ctx.config.identity.roles,
      tenant: ctx.config.tenant,
    },
    tool: "retrieve_for_context",
    query: args.query,
    ...(args.top_k !== undefined ? { top_k: args.top_k } : {}),
    ...(args.token_budget !== undefined ? { token_budget: args.token_budget } : {}),
    ...(args.filters !== undefined ? { filters: args.filters } : {}),
  };
  return await ctx.pipeline.retrieve(req);
}
