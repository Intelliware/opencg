import { createServer, type Server as HttpServer } from "node:http";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { request as undiciRequest } from "undici";
import { afterEach, describe, expect, it } from "vitest";
import { Authenticator } from "./auth.js";
import { loadConfig } from "./config.js";
import { buildMcpServer, handleMcpHttp } from "./server.js";

function ctx(httpToken: string | null = null) {
  const config = loadConfig({
    OPENCG__IDENTITY__PRINCIPAL: "t",
    OPENCG__IDENTITY__ROLES: "reader",
    OPENCG__PIPELINE__URL: "http://unused",
    OPENCG__ENVIRONMENT: "dev",
    ...(httpToken ? { OPENCG__MCP__HTTP_TOKEN: httpToken } : {}),
  });
  const pipeline = {
    retrieve: async () => ({}),
    traverse: async () => ({ nodes: [], edges: [] }),
    health: async () => true,
  } as never;
  return { config, pipeline, authenticator: new Authenticator(config) };
}

const FIVE_TOOLS = [
  "opencg/get_entity",
  "opencg/retrieve_for_context",
  "opencg/search",
  "opencg/submit_feedback",
  "opencg/traverse_graph",
];

describe("buildMcpServer", () => {
  it("advertises the five opencg tools over an in-memory client", async () => {
    const server = buildMcpServer(ctx());
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport);
    const client = new Client({ name: "test", version: "0" }, { capabilities: {} });
    await client.connect(clientTransport);
    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name).sort()).toEqual([...FIVE_TOOLS].sort());
    await client.close();
  });
});

describe("handleMcpHttp", () => {
  let http: HttpServer | null = null;

  afterEach(() => {
    http?.close();
    http = null;
  });

  async function start(token: string | null) {
    const c = ctx(token);
    http = createServer((req, res) => {
      if ((req.url ?? "").split("?")[0] === "/mcp") void handleMcpHttp(req, res, c);
      else {
        res.writeHead(404);
        res.end();
      }
    });
    await new Promise<void>((resolve) => http!.listen(0, resolve));
    const addr = http!.address();
    const port = typeof addr === "object" && addr ? addr.port : 0;
    return `http://127.0.0.1:${port}/mcp`;
  }

  const initBody = JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "t", version: "0" } },
  });
  const headers = { "content-type": "application/json", accept: "application/json, text/event-stream" };

  it("completes initialize then tools/list over a session (open mode)", async () => {
    const url = await start(null);
    const res = await undiciRequest(url, { method: "POST", headers, body: initBody });
    expect(res.statusCode).toBe(200);
    const sessionId = res.headers["mcp-session-id"] as string | undefined;
    expect(sessionId).toBeTruthy();
    expect(await res.body.text()).toContain("opencg");

    // Follow-up request on the same session must reach an initialized server.
    const res2 = await undiciRequest(url, {
      method: "POST",
      headers: { ...headers, "mcp-session-id": sessionId! },
      body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" }),
    });
    expect(res2.statusCode).toBe(200);
    const text2 = await res2.body.text();
    for (const tool of FIVE_TOOLS) expect(text2).toContain(tool);
  });

  it("rejects a follow-up with no/unknown session", async () => {
    const url = await start(null);
    const res = await undiciRequest(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ jsonrpc: "2.0", id: 9, method: "tools/list" }),
    });
    expect(res.statusCode).toBe(400);
    await res.body.text();
  });

  it("returns 401 when a token is set and the bearer is missing", async () => {
    const url = await start("s3cret");
    const res = await undiciRequest(url, { method: "POST", headers, body: initBody });
    expect(res.statusCode).toBe(401);
    await res.body.text();
  });

  it("accepts the request when the correct bearer is provided", async () => {
    const url = await start("s3cret");
    const res = await undiciRequest(url, {
      method: "POST",
      headers: { ...headers, authorization: "Bearer s3cret" },
      body: initBody,
    });
    expect(res.statusCode).toBe(200);
    expect(await res.body.text()).toContain("serverInfo");
  });
});
