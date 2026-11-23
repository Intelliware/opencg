import type { Server as HttpServer } from "node:http";
import type { AddressInfo } from "node:net";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { request as undiciRequest } from "undici";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { Authenticator } from "./auth.js";
import { loadConfig, type McpConfig } from "./config.js";
import { createHttpApp } from "./http-app.js";
import { PipelineClient, PipelineRequestError } from "./pipeline-client.js";
import { buildMcpServer, classifyError, instrumentedCallTool, toolErrorCode } from "./server.js";
import { installInMemoryExporterForTests } from "./telemetry.js";
import { type FakePipelineServer, startFakePipeline, startTestIdp, type TestIdp } from "./test-idp.js";

const PUBLIC_URL = "https://mcp.example.test";
const HEADERS = { "content-type": "application/json", accept: "application/json, text/event-stream" };
const INIT = JSON.stringify({
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t", version: "0" } },
});

let idp: TestIdp;
let pipeline: FakePipelineServer;
let http: HttpServer | null = null;

beforeAll(async () => {
  idp = await startTestIdp();
  pipeline = await startFakePipeline();
});
afterAll(async () => {
  await idp.close();
  await pipeline.close();
});
afterEach(() => {
  http?.close();
  http = null;
  pipeline.requests = [];
  pipeline.respond = { status: 200, body: null };
});

function oidcConfig(extra: Record<string, string> = {}): McpConfig {
  return loadConfig({
    OPENCG__AUTH__MODE: "oidc",
    OPENCG__AUTH__OIDC__ISSUER: idp.url,
    OPENCG__MCP__PUBLIC_URL: PUBLIC_URL,
    OPENCG__PIPELINE__URL: pipeline.url,
    ...extra,
  });
}

async function start(config: McpConfig): Promise<string> {
  http = createHttpApp({
    config,
    pipeline: new PipelineClient(config.pipelineUrl),
    authenticator: new Authenticator(config),
  }).listen(0, "127.0.0.1");
  await new Promise<void>((resolve) => http!.once("listening", resolve));
  return `http://127.0.0.1:${(http.address() as AddressInfo).port}`;
}

/** Parse a JSON or single-event SSE response body. */
function rpc(text: string): any {
  const data = text.split("\n").find((l) => l.startsWith("data: "));
  return JSON.parse(data ? data.slice(6) : text);
}

async function session(base: string, authorization: string): Promise<string> {
  const res = await undiciRequest(`${base}/mcp`, {
    method: "POST",
    headers: { ...HEADERS, authorization },
    body: INIT,
  });
  expect(res.statusCode).toBe(200);
  await res.body.text();
  return res.headers["mcp-session-id"] as string;
}

async function call(
  base: string,
  sid: string,
  authorization: string,
  name: string,
  args: Record<string, unknown>,
  extraHeaders: Record<string, string> = {},
): Promise<any> {
  const res = await undiciRequest(`${base}/mcp`, {
    method: "POST",
    headers: { ...HEADERS, ...extraHeaders, authorization, "mcp-session-id": sid },
    body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name, arguments: args } }),
  });
  expect(res.statusCode).toBe(200);
  return rpc(await res.body.text()).result;
}

describe("oidc mode over HTTP", () => {
  it("serves protected-resource metadata pointing at the issuer (bare and /mcp-suffixed)", async () => {
    const base = await start(oidcConfig());
    for (const path of ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"]) {
      const res = await undiciRequest(`${base}${path}`);
      expect(res.statusCode).toBe(200);
      expect(await res.body.json()).toEqual({
        resource: `${PUBLIC_URL}/mcp`,
        authorization_servers: [idp.url],
        bearer_methods_supported: ["header"],
        scopes_supported: ["openid"],
      });
    }
  });

  it("returns 404 for the removed self-issued OAuth routes", async () => {
    const base = await start(oidcConfig());
    for (const [method, path] of [
      ["GET", "/.well-known/oauth-authorization-server"],
      ["GET", "/authorize"],
      ["POST", "/token"],
      ["POST", "/register"],
      ["POST", "/revoke"],
      ["POST", "/oauth/approve"],
    ] as const) {
      const res = await undiciRequest(`${base}${path}`, { method });
      expect(res.statusCode, `${method} ${path}`).toBe(404);
      await res.body.text();
    }
  });

  it("keeps health and metrics unauthenticated", async () => {
    const base = await start(oidcConfig());
    for (const path of ["/healthz", "/metrics"]) {
      const res = await undiciRequest(`${base}${path}`);
      expect(res.statusCode).toBe(200);
      await res.body.text();
    }
  });

  it("answers 401 with resource_metadata when the token is missing, plus invalid_token when bad", async () => {
    const base = await start(oidcConfig());
    const missing = await undiciRequest(`${base}/mcp`, { method: "POST", headers: HEADERS, body: INIT });
    expect(missing.statusCode).toBe(401);
    expect(missing.headers["www-authenticate"]).toBe(
      `Bearer resource_metadata="${PUBLIC_URL}/.well-known/oauth-protected-resource"`,
    );
    expect((await missing.body.json()) as any).toMatchObject({ error: { data: { code: "token_missing" } } });

    const expired = await idp.sign({ preferred_username: "alice" }, { expiresIn: -600 });
    const bad = await undiciRequest(`${base}/mcp`, {
      method: "POST",
      headers: { ...HEADERS, authorization: `Bearer ${expired}` },
      body: INIT,
    });
    expect(bad.statusCode).toBe(401);
    expect(bad.headers["www-authenticate"]).toBe(
      `Bearer resource_metadata="${PUBLIC_URL}/.well-known/oauth-protected-resource", error="invalid_token"`,
    );
    expect((await bad.body.json()) as any).toMatchObject({ error: { data: { code: "token_expired" } } });
  });

  it("runs initialize, tools/list and tools/call with a valid token, forwarding it to the pipeline", async () => {
    const base = await start(oidcConfig());
    const token = await idp.sign({ preferred_username: "alice", roles: ["reader"] });
    const authz = `Bearer ${token}`;
    const sid = await session(base, authz);

    const list = await undiciRequest(`${base}/mcp`, {
      method: "POST",
      headers: { ...HEADERS, authorization: authz, "mcp-session-id": sid },
      body: JSON.stringify({ jsonrpc: "2.0", id: 3, method: "tools/list" }),
    });
    expect(await list.body.text()).toContain("opencg/retrieve_for_context");

    const retrieved = await call(base, sid, authz, "opencg/retrieve_for_context", { query: "q" }, {
      "x-correlation-id": "abc-123",
    });
    expect(retrieved.isError).toBeUndefined();
    const traversed = await call(base, sid, authz, "opencg/traverse_graph", { concept_id: "c1" });
    expect(traversed.isError).toBeUndefined();

    expect(pipeline.requests.map((r) => r.path)).toEqual(["/retrieve", "/graph/traverse"]);
    for (const r of pipeline.requests) expect(r.authorization).toBe(authz);
    expect(pipeline.requests[0]?.correlationId).toBe("abc-123");
  });

  it.each([
    [401, { code: "token_invalid" }, "unauthenticated"],
    [403, { detail: { code: "forbidden" } }, "forbidden"],
    [503, { code: "policy_unavailable" }, "policy_unavailable"],
    [503, { code: "something_else" }, "error"],
  ])("maps a pipeline %i %j to the tool error code %s", async (status, body, code) => {
    const base = await start(oidcConfig());
    const authz = `Bearer ${await idp.sign({ preferred_username: "bob" })}`;
    const sid = await session(base, authz);
    pipeline.respond = { status, body };
    const result = await call(base, sid, authz, "opencg/traverse_graph", { concept_id: "c1" });
    expect(result.isError).toBe(true);
    expect(JSON.parse(result.content[0].text).code).toBe(code);
  });
});

describe("none mode over HTTP", () => {
  it("is open, sends no Authorization to the pipeline, and serves no resource metadata", async () => {
    const base = await start(loadConfig({ OPENCG__PIPELINE__URL: pipeline.url }));
    const meta = await undiciRequest(`${base}/.well-known/oauth-protected-resource`);
    expect(meta.statusCode).toBe(404);
    await meta.body.text();
    const res = await undiciRequest(`${base}/mcp`, { method: "POST", headers: HEADERS, body: INIT });
    const sid = res.headers["mcp-session-id"] as string;
    await res.body.text();
    const result = await call(base, sid, "", "opencg/retrieve_for_context", { query: "q" });
    expect(result.isError).toBeUndefined();
    expect(pipeline.requests[0]?.authorization).toBeUndefined();
  });

  it("dev: accepts the legacy HTTP token and forwards it; rejects a wrong one", async () => {
    const base = await start(
      loadConfig({ OPENCG__PIPELINE__URL: pipeline.url, OPENCG__ENVIRONMENT: "dev", OPENCG__MCP__HTTP_TOKEN: "s3cret" }),
    );
    const wrong = await undiciRequest(`${base}/mcp`, {
      method: "POST",
      headers: { ...HEADERS, authorization: "Bearer nope" },
      body: INIT,
    });
    expect(wrong.statusCode).toBe(401);
    expect(wrong.headers["www-authenticate"]).toBe('Bearer realm="opencg", error="invalid_token"');
    await wrong.body.text();
    const sid = await session(base, "Bearer s3cret");
    await call(base, sid, "Bearer s3cret", "opencg/traverse_graph", { concept_id: "c1" });
    expect(pipeline.requests[0]?.authorization).toBe("Bearer s3cret");
  });
});

describe("stdio transport", () => {
  async function connect(resolveCaller?: () => ReturnType<Authenticator["authenticate"]>) {
    const config = oidcConfig();
    const server = buildMcpServer({
      config,
      pipeline: new PipelineClient(pipeline.url),
      ...(resolveCaller ? { resolveCaller } : {}),
    });
    const [clientT, serverT] = InMemoryTransport.createLinkedPair();
    await server.connect(serverT);
    const client = new Client({ name: "t", version: "0" }, { capabilities: {} });
    await client.connect(clientT);
    return client;
  }

  it("oidc without OPENCG__MCP__STDIO_TOKEN: lists tools but fails calls with unauthenticated", async () => {
    const auth = new Authenticator(oidcConfig());
    const client = await connect(() => auth.authenticate(undefined));
    expect((await client.listTools()).tools.length).toBe(5);
    const result = (await client.callTool({
      name: "opencg/retrieve_for_context",
      arguments: { query: "q" },
    })) as any;
    expect(result.isError).toBe(true);
    expect(JSON.parse(result.content[0].text).code).toBe("unauthenticated");
    expect(pipeline.requests).toHaveLength(0);
    await client.close();
  });

  it("oidc with a valid stdio token forwards it", async () => {
    const auth = new Authenticator(oidcConfig());
    const token = await idp.sign({ preferred_username: "carol" });
    const client = await connect(() => auth.authenticate(`Bearer ${token}`));
    const result = (await client.callTool({ name: "opencg/traverse_graph", arguments: { concept_id: "c" } })) as any;
    expect(result.isError).toBeUndefined();
    expect(pipeline.requests[0]?.authorization).toBe(`Bearer ${token}`);
    await client.close();
  });
});

describe("error classification", () => {
  it("counts 401/403 as rejected and a policy 503 as error", () => {
    expect(classifyError(new PipelineRequestError(401, "{}"))).toBe("rejected");
    expect(classifyError(new PipelineRequestError(403, "{}"))).toBe("rejected");
    const policy = new PipelineRequestError(503, '{"code":"policy_unavailable"}');
    expect(classifyError(policy)).toBe("error");
    expect(toolErrorCode(policy)).toBe("policy_unavailable");
    expect(toolErrorCode(new PipelineRequestError(500, "boom"))).toBe("error");
  });
});

describe("mcp.<tool> span", () => {
  it("records principal and auth_method", async () => {
    const exporter = installInMemoryExporterForTests({ OTEL_EXPORTER_OTLP_ENDPOINT: "none" });
    const config = oidcConfig();
    await instrumentedCallTool("opencg/traverse_graph", { concept_id: "c" }, {
      config,
      pipeline: new PipelineClient(pipeline.url),
      caller: { principal: "alice", roles: [], tenant: "default", authMethod: "oidc", authorization: "Bearer x" },
    });
    const span = exporter.getFinishedSpans().find((s) => s.name === "mcp.traverse_graph");
    expect(span?.attributes.principal).toBe("alice");
    expect(span?.attributes.auth_method).toBe("oidc");
  });
});
