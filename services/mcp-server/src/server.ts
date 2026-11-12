// MCP server wiring shared by both transports. `buildMcpServer` registers the
// tool handlers on a fresh `Server`; stdio connects one, and each HTTP session
// connects its own. `handleMcpHttp` authenticates every `/mcp` request (see
// src/auth.ts) and hands the caller to the tool handlers through the SDK's
// `req.auth` → `extra.authInfo` channel, so each request runs as whoever sent
// it, even within one session.

import { randomUUID } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import type { AuthInfo } from "@modelcontextprotocol/sdk/server/auth/types.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  isInitializeRequest,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import type { AuthFailureReason, AuthResult, Authenticator, Caller } from "./auth.js";
import { type Outcome, recordToolCall } from "./metrics.js";
import { PipelineRequestError } from "./pipeline-client.js";
import { withSpan } from "./telemetry.js";
import {
  ConceptNotFoundError,
  NotImplementedInMvpError,
  TOOL_DEFINITIONS,
  type ToolCallContext,
  ToolValidationError,
  UnauthenticatedError,
  UnknownToolError,
  callTool,
  toolLabel,
} from "./tools.js";

export interface McpServerContext extends ToolCallContext {
  /**
   * Resolves the caller for each tool call when no HTTP auth info is attached
   * (stdio in `oidc` mode: verifies OPENCG__MCP__STDIO_TOKEN per call, so an
   * expired token fails the call instead of the server).
   */
  resolveCaller?: () => Promise<AuthResult>;
}

export interface HttpContext extends ToolCallContext {
  authenticator: Authenticator;
}

// `rejected` = the caller's request was refused (bad arguments, unknown or
// unimplemented tool, a 4xx from the pipeline such as validation or a policy
// denial). `error` = anything else (pipeline 5xx, network failure, bug).
export function classifyError(err: unknown): Outcome {
  if (
    err instanceof ToolValidationError ||
    err instanceof UnauthenticatedError ||
    err instanceof UnknownToolError ||
    err instanceof NotImplementedInMvpError ||
    err instanceof ConceptNotFoundError
  ) {
    return "rejected";
  }
  if (err instanceof PipelineRequestError && err.statusCode >= 400 && err.statusCode < 500) {
    return "rejected";
  }
  return "error";
}

/**
 * Tool-error `code` returned to the MCP client. Pipeline auth failures map to
 * `unauthenticated` (401), `forbidden` (403) and `policy_unavailable` (503 with
 * that code); the tool's own errors keep their codes; anything else is `error`.
 */
export function toolErrorCode(err: unknown): string {
  if (
    err instanceof NotImplementedInMvpError ||
    err instanceof ConceptNotFoundError ||
    err instanceof UnauthenticatedError
  ) {
    return err.code;
  }
  if (err instanceof PipelineRequestError) {
    if (err.statusCode === 401) return "unauthenticated";
    if (err.statusCode === 403) return "forbidden";
    if (err.statusCode === 503 && err.errorCode === "policy_unavailable") return "policy_unavailable";
  }
  return "error";
}

const CORRELATION_ID = /^[A-Za-z0-9._:-]{1,128}$/;

/** The caller's `x-correlation-id` when it is a sane token, else undefined. */
export function callerCorrelationId(
  headers: Record<string, string | string[] | undefined> | undefined,
): string | undefined {
  const raw = headers?.["x-correlation-id"];
  const value = (Array.isArray(raw) ? raw[0] : raw)?.trim();
  return value && CORRELATION_ID.test(value) ? value : undefined;
}

/**
 * Run one tool call inside an `mcp.<tool>` span and record
 * `opencg_requests_total{tool,outcome}` + `opencg_stage_latency_seconds{stage="mcp"}`.
 * The correlation ID minted here is the one sent to the pipeline (request body
 * and `x-correlation-id`), so MCP and pipeline spans share it.
 */
export async function instrumentedCallTool(
  name: string,
  args: unknown,
  ctx: ToolCallContext,
  authFailure: AuthFailureReason | null = null,
): Promise<Awaited<ReturnType<typeof callTool>>> {
  const tool = toolLabel(name);
  const correlationId = ctx.correlationId || randomUUID();
  const started = process.hrtime.bigint();
  let outcome: Outcome = "ok";
  const caller = ctx.caller;
  try {
    return await withSpan(
      `mcp.${tool}`,
      {
        correlation_id: correlationId,
        tool,
        tenant: caller?.tenant ?? ctx.config.tenant,
        principal: caller?.principal ?? (authFailure ? "" : ctx.config.identity.principal),
        auth_method: caller?.authMethod ?? (authFailure ? "unauthenticated" : "none"),
      },
      async (span) => {
        try {
          if (authFailure) throw new UnauthenticatedError(`authentication failed: ${authFailure}`);
          return await callTool(name, args, { ...ctx, correlationId });
        } catch (err) {
          outcome = classifyError(err);
          span.setAttribute("outcome", outcome);
          throw err;
        }
      },
    );
  } catch (err) {
    if (outcome === "ok") outcome = classifyError(err);
    throw err;
  } finally {
    recordToolCall(tool, outcome, Number(process.hrtime.bigint() - started) / 1e9);
  }
}

export function buildMcpServer(ctx: McpServerContext): Server {
  const server = new Server(
    { name: "opencg", version: "0.0.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: TOOL_DEFINITIONS.map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req, extra) => {
    try {
      let caller = extra.authInfo?.extra?.caller as Caller | undefined;
      let authFailure: AuthFailureReason | null = null;
      if (!caller && ctx.resolveCaller) {
        const resolved = await ctx.resolveCaller();
        if (resolved.ok) caller = resolved.caller;
        else authFailure = resolved.reason;
      }
      const correlationId = callerCorrelationId(extra.requestInfo?.headers) ?? ctx.correlationId;
      const callCtx: ToolCallContext = {
        config: ctx.config,
        pipeline: ctx.pipeline,
        ...(caller ? { caller } : {}),
        ...(correlationId ? { correlationId } : {}),
      };
      const result = await instrumentedCallTool(
        req.params.name,
        req.params.arguments ?? {},
        callCtx,
        authFailure,
      );
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (err) {
      const code = toolErrorCode(err);
      const message = err instanceof Error ? err.message : String(err);
      return {
        isError: true,
        content: [{ type: "text", text: JSON.stringify({ code, message }) }],
      };
    }
  });

  return server;
}

async function readJsonBody(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  if (chunks.length === 0) return undefined;
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return undefined;
  }
}

// Live Streamable HTTP sessions, keyed by `mcp-session-id`. A real client does
// `initialize` (no session id) → gets an id back → reuses it on follow-up
// requests, so each session's server stays initialized across requests.
const transports = new Map<string, StreamableHTTPServerTransport>();

/** `WWW-Authenticate` for a `/mcp` 401 (RFC 6750 + RFC 9728 `resource_metadata`). */
export function wwwAuthenticate(ctx: ToolCallContext, tokenPresent: boolean): string {
  const params =
    ctx.config.authMode === "oidc"
      ? [`resource_metadata="${ctx.config.publicUrl}/.well-known/oauth-protected-resource"`]
      : ['realm="opencg"'];
  if (tokenPresent) params.push('error="invalid_token"');
  return `Bearer ${params.join(", ")}`;
}

// Handle one `/mcp` request: authenticate, then dispatch to the session.
export async function handleMcpHttp(
  req: IncomingMessage,
  res: ServerResponse,
  ctx: HttpContext,
): Promise<void> {
  const result = await ctx.authenticator.authenticate(req.headers.authorization);
  if (!result.ok) {
    res.writeHead(401, {
      "content-type": "application/json",
      "www-authenticate": wwwAuthenticate(ctx, result.tokenPresent),
    });
    res.end(
      JSON.stringify({
        jsonrpc: "2.0",
        error: { code: -32001, message: "unauthorized", data: { code: result.reason } },
        id: null,
      }),
    );
    return;
  }
  const authInfo: AuthInfo = {
    // The credential itself travels in `caller.authorization`; keep it out of
    // the generic field so nothing logs it by accident.
    token: "",
    clientId: result.caller.keyName ?? result.caller.principal,
    scopes: [],
    extra: { caller: result.caller },
  };
  (req as IncomingMessage & { auth?: AuthInfo }).auth = authInfo;
  await dispatchMcp(req, res, ctx);
}

// Route an already-authenticated `/mcp` request to its Streamable HTTP session.
export async function dispatchMcp(
  req: IncomingMessage,
  res: ServerResponse,
  ctx: ToolCallContext,
): Promise<void> {
  const sessionId = req.headers["mcp-session-id"] as string | undefined;

  // Follow-up request for an existing session (POST call, GET SSE, or DELETE).
  if (sessionId && transports.has(sessionId)) {
    const transport = transports.get(sessionId)!;
    const body = req.method === "POST" ? await readJsonBody(req) : undefined;
    await transport.handleRequest(req, res, body);
    return;
  }

  // A new session must begin with an `initialize` POST.
  if (req.method === "POST") {
    const body = await readJsonBody(req);
    if (!sessionId && isInitializeRequest(body)) {
      // The transport's option/`onclose` typing differs from the `Transport`
      // interface under `exactOptionalPropertyTypes`; the two casts below are
      // the SDK's documented usage, isolated to this boundary.
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (sid: string) => transports.set(sid, transport),
      } as unknown as ConstructorParameters<typeof StreamableHTTPServerTransport>[0]);
      transport.onclose = () => {
        if (transport.sessionId) transports.delete(transport.sessionId);
      };
      const server = buildMcpServer({ config: ctx.config, pipeline: ctx.pipeline });
      await server.connect(transport as unknown as Parameters<typeof server.connect>[0]);
      await transport.handleRequest(req, res, body);
      return;
    }
  }

  res.writeHead(400, { "content-type": "application/json" });
  res.end(
    JSON.stringify({
      jsonrpc: "2.0",
      error: { code: -32000, message: "missing or invalid mcp session" },
      id: null,
    }),
  );
}
