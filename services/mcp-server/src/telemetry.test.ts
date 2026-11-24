import { createServer, type IncomingHttpHeaders, type Server as HttpServer } from "node:http";
import type { AddressInfo } from "node:net";
import type { InMemorySpanExporter } from "@opentelemetry/sdk-trace";
import { request as undiciRequest } from "undici";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Authenticator } from "./auth.js";
import { loadConfig, type McpConfig } from "./config.js";
import { createHttpApp } from "./http-app.js";
import { requestsTotal, stageLatencySeconds } from "./metrics.js";
import { PipelineClient } from "./pipeline-client.js";
import { instrumentedCallTool } from "./server.js";
import {
  exportDisabled,
  installInMemoryExporterForTests,
  resolveEndpoint,
  serviceNamespace,
} from "./telemetry.js";

function config(httpToken: string | null = null): McpConfig {
  return loadConfig({
    OPENCG__TENANT: "acme",
    OPENCG__IDENTITY__PRINCIPAL: "t",
    OPENCG__IDENTITY__ROLES: "reader",
    OPENCG__PIPELINE__URL: "http://unused",
    OPENCG__MCP__PORT: "0",
    OPENCG__ENVIRONMENT: "dev",
    ...(httpToken ? { OPENCG__MCP__HTTP_TOKEN: httpToken } : {}),
  });
}

async function count(tool: string, outcome: string): Promise<number> {
  const { values } = await requestsTotal.get();
  const labels = (v: (typeof values)[number]) => v.labels as Record<string, string | number>;
  return (
    values.find((v) => labels(v).tool === tool && labels(v).outcome === outcome)?.value ?? 0
  );
}

async function mcpLatencyCount(): Promise<number> {
  const { values } = await stageLatencySeconds.get();
  return (
    values.find(
      (v) => v.metricName === "opencg_stage_latency_seconds_count" && v.labels.stage === "mcp",
    )?.value ?? 0
  );
}

// A stand-in pipeline that records request headers and answers with `status`.
interface FakePipeline {
  url: string;
  seen: { headers: IncomingHttpHeaders; body: string }[];
  close: () => void;
}

async function fakePipeline(status = 200): Promise<FakePipeline> {
  const seen: FakePipeline["seen"] = [];
  const server: HttpServer = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      seen.push({ headers: req.headers, body: Buffer.concat(chunks).toString("utf8") });
      res.writeHead(status, { "content-type": "application/json" });
      res.end(status < 400 ? JSON.stringify({ fragments: [], usage: {} }) : '{"detail":"boom"}');
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return { url: `http://127.0.0.1:${port}`, seen, close: () => server.close() };
}

let exporter: InMemorySpanExporter;

beforeEach(() => {
  exporter = installInMemoryExporterForTests({ OPENCG__TELEMETRY__SERVICE_NAMESPACE: "test-ns" });
});

describe("endpoint resolution", () => {
  it("defaults to the compose collector and honours the disable values", () => {
    expect(resolveEndpoint({})).toBe("http://otel-collector:4318");
    expect(resolveEndpoint({ OTEL_EXPORTER_OTLP_ENDPOINT: "" })).toBe("");
    for (const v of ["none", "OFF", "disabled", "", "  "]) expect(exportDisabled(v)).toBe(true);
    expect(exportDisabled("http://otel-collector:4318")).toBe(false);
    expect(serviceNamespace({})).toBe("opencg");
  });
});

describe("tool spans", () => {
  let pipeline: FakePipeline | null = null;
  afterEach(() => pipeline?.close());

  it("emits mcp.<tool> with correlation_id, tool and tenant on the service resource", async () => {
    pipeline = await fakePipeline();
    const ctx = { config: config(), pipeline: new PipelineClient(pipeline.url) };
    await instrumentedCallTool("opencg/retrieve_for_context", { query: "hello" }, ctx);

    const spans = exporter.getFinishedSpans();
    expect(spans.map((s) => s.name)).toEqual(["mcp.retrieve_for_context"]);
    const span = spans[0]!;
    expect(span.attributes.tool).toBe("retrieve_for_context");
    expect(span.attributes.tenant).toBe("acme");
    expect(typeof span.attributes.correlation_id).toBe("string");
    expect(span.resource.attributes["service.name"]).toBe("opencg-mcp-server");
    expect(span.resource.attributes["service.namespace"]).toBe("test-ns");
  });

  it("sends traceparent and the same correlation ID to the pipeline", async () => {
    pipeline = await fakePipeline();
    const ctx = { config: config(), pipeline: new PipelineClient(pipeline.url) };
    await instrumentedCallTool("opencg/retrieve_for_context", { query: "hello" }, ctx);

    const span = exporter.getFinishedSpans()[0]!;
    const { traceId, spanId } = span.spanContext();
    const sent = pipeline.seen[0]!;
    expect(sent.headers.traceparent).toBe(`00-${traceId}-${spanId}-01`);
    expect(sent.headers["x-correlation-id"]).toBe(span.attributes.correlation_id);
    expect(JSON.parse(sent.body).correlation_id).toBe(span.attributes.correlation_id);
  });

  it("propagates traceparent on traverse_graph too", async () => {
    pipeline = await fakePipeline();
    const ctx = { config: config(), pipeline: new PipelineClient(pipeline.url) };
    await instrumentedCallTool("opencg/traverse_graph", { concept_id: "c1" }, ctx);
    const span = exporter.getFinishedSpans()[0]!;
    expect(span.name).toBe("mcp.traverse_graph");
    expect(pipeline.seen[0]!.headers.traceparent).toContain(span.spanContext().traceId);
    expect(pipeline.seen[0]!.headers["x-correlation-id"]).toBe(span.attributes.correlation_id);
  });
});

describe("tool metrics", () => {
  let pipeline: FakePipeline | null = null;
  afterEach(() => pipeline?.close());

  it("counts ok calls and observes mcp stage latency", async () => {
    pipeline = await fakePipeline();
    const ctx = { config: config(), pipeline: new PipelineClient(pipeline.url) };
    const before = await count("retrieve_for_context", "ok");
    const latencyBefore = await mcpLatencyCount();
    await instrumentedCallTool("opencg/retrieve_for_context", { query: "q" }, ctx);
    expect(await count("retrieve_for_context", "ok")).toBe(before + 1);
    expect(await mcpLatencyCount()).toBe(latencyBefore + 1);
  });

  it("counts a pipeline 5xx as error and marks the span", async () => {
    pipeline = await fakePipeline(500);
    const ctx = { config: config(), pipeline: new PipelineClient(pipeline.url) };
    const before = await count("retrieve_for_context", "error");
    await expect(
      instrumentedCallTool("opencg/retrieve_for_context", { query: "q" }, ctx),
    ).rejects.toThrow(/pipeline 500/);
    expect(await count("retrieve_for_context", "error")).toBe(before + 1);
    const span = exporter.getFinishedSpans()[0]!;
    expect(span.status.code).toBe(2); // SpanStatusCode.ERROR
    expect(span.attributes.outcome).toBe("error");
  });

  it("counts validation failures and unknown tools as rejected with bounded labels", async () => {
    const ctx = { config: config(), pipeline: new PipelineClient("http://127.0.0.1:1") };
    const before = await count("retrieve_for_context", "rejected");
    await expect(instrumentedCallTool("opencg/retrieve_for_context", {}, ctx)).rejects.toThrow();
    expect(await count("retrieve_for_context", "rejected")).toBe(before + 1);

    const unknownBefore = await count("unknown", "rejected");
    await expect(instrumentedCallTool("some/arbitrary-name", {}, ctx)).rejects.toThrow();
    expect(await count("unknown", "rejected")).toBe(unknownBefore + 1);
    expect(exporter.getFinishedSpans().map((s) => s.name)).toContain("mcp.unknown");
  });
});

describe("HTTP /metrics", () => {
  let http: HttpServer | null = null;
  afterEach(() => {
    http?.close();
    http = null;
  });

  async function start(token: string | null): Promise<string> {
    const cfg = config(token);
    const ctx = {
      config: cfg,
      pipeline: new PipelineClient("http://127.0.0.1:1"),
      authenticator: new Authenticator(cfg),
    };
    http = createHttpApp(ctx).listen(0, "127.0.0.1");
    await new Promise<void>((resolve) => http!.once("listening", resolve));
    return `http://127.0.0.1:${(http.address() as AddressInfo).port}`;
  }

  it("serves Prometheus text without the bearer token while /mcp still requires it", async () => {
    const base = await start("s3cret");
    const rejectedBefore = await count("unknown", "rejected");

    const mcp = await undiciRequest(`${base}/mcp`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
    });
    expect(mcp.statusCode).toBe(401);
    await mcp.body.text();

    const res = await undiciRequest(`${base}/metrics`);
    expect(res.statusCode).toBe(200);
    expect(String(res.headers["content-type"])).toContain("text/plain");
    const text = await res.body.text();
    expect(text).toContain("# TYPE opencg_requests_total counter");
    expect(text).toContain("# TYPE opencg_stage_latency_seconds histogram");
    expect(text).toContain('opencg_stage_latency_seconds_bucket{le="30",stage="mcp"}');
    // No default Node process metrics on the private registry.
    expect(text).not.toContain("process_cpu");
    expect(text).not.toContain("nodejs_");
    expect(await count("unknown", "rejected")).toBe(rejectedBefore + 1);
  });
});
