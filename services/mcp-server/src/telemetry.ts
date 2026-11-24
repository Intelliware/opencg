// OpenTelemetry bootstrap for the MCP server. Mirrors `setup_otel()` in
// `opencg_shared.otel`: the same endpoint env var, default and disable values.
//
// Nothing here writes to stdout (stdout is the MCP stdio channel). The OTel
// diag logger is left at its no-op default, so a missing collector never
// produces log lines; the exporter drops failed batches without logging.

import {
  type Attributes,
  context,
  propagation,
  type Span,
  SpanStatusCode,
  trace,
} from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import { W3CTraceContextPropagator } from "@opentelemetry/core";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { defaultResource, resourceFromAttributes } from "@opentelemetry/resources";
import {
  BatchSpanProcessor,
  InMemorySpanExporter,
  SimpleSpanProcessor,
  type SpanProcessor,
  TracerProvider,
} from "@opentelemetry/sdk-trace";

export const SERVICE_NAME = "opencg-mcp-server";
export const DEFAULT_ENDPOINT = "http://otel-collector:4318";
const DISABLED_ENDPOINTS = new Set(["none", "off", "disabled", ""]);

/** `OTEL_EXPORTER_OTLP_ENDPOINT` when set (even to empty), else the compose default. */
export function resolveEndpoint(env: NodeJS.ProcessEnv = process.env): string {
  const value = env.OTEL_EXPORTER_OTLP_ENDPOINT;
  return value === undefined ? DEFAULT_ENDPOINT : value;
}

export function exportDisabled(endpoint: string): boolean {
  return DISABLED_ENDPOINTS.has(endpoint.trim().toLowerCase());
}

export function serviceNamespace(env: NodeJS.ProcessEnv = process.env): string {
  return (env.OPENCG__TELEMETRY__SERVICE_NAMESPACE ?? "").trim() || "opencg";
}

let provider: TracerProvider | null = null;
let contextManager: AsyncLocalStorageContextManager | null = null;

function install(processors: SpanProcessor[], env: NodeJS.ProcessEnv): TracerProvider {
  // Tear down any earlier install so the global setters accept the new one.
  void provider?.shutdown().catch(() => undefined);
  contextManager?.disable();
  trace.disable();
  context.disable();
  propagation.disable();

  const resource = defaultResource().merge(
    resourceFromAttributes({
      "service.name": SERVICE_NAME,
      "service.namespace": serviceNamespace(env),
    }),
  );
  provider = new TracerProvider({ resource, spanProcessors: processors });
  contextManager = new AsyncLocalStorageContextManager().enable();
  context.setGlobalContextManager(contextManager);
  propagation.setGlobalPropagator(new W3CTraceContextPropagator());
  trace.setGlobalTracerProvider(provider);
  return provider;
}

/**
 * Initialise tracing once at start-up (both transports). When export is
 * disabled a provider is still installed without any processor, so spans get
 * real IDs and `traceparent` still flows to the pipeline, but nothing leaves
 * the process.
 */
export function initTelemetry(env: NodeJS.ProcessEnv = process.env): void {
  const endpoint = resolveEndpoint(env);
  const processors: SpanProcessor[] = [];
  if (!exportDisabled(endpoint)) {
    const exporter = new OTLPTraceExporter({ url: `${endpoint.replace(/\/+$/, "")}/v1/traces` });
    processors.push(new BatchSpanProcessor({ exporter }));
  }
  install(processors, env);
}

/** Flush pending spans and stop the exporter (best effort). */
export async function shutdownTelemetry(): Promise<void> {
  try {
    await provider?.shutdown();
  } catch {
    // Collector unreachable at shutdown: drop silently.
  }
}

/** Test hook: install a provider that records spans in memory. */
export function installInMemoryExporterForTests(
  env: NodeJS.ProcessEnv = process.env,
): InMemorySpanExporter {
  const exporter = new InMemorySpanExporter();
  install([new SimpleSpanProcessor({ exporter })], env);
  return exporter;
}

export function tracer() {
  return trace.getTracer(SERVICE_NAME);
}

/** Run `fn` inside a new active span; records exceptions and ends the span. */
export async function withSpan<T>(
  name: string,
  attributes: Attributes,
  fn: (span: Span) => Promise<T>,
): Promise<T> {
  return tracer().startActiveSpan(name, { attributes }, async (span) => {
    try {
      return await fn(span);
    } catch (err) {
      span.recordException(err instanceof Error ? err : String(err));
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: err instanceof Error ? err.message : String(err),
      });
      throw err;
    } finally {
      span.end();
    }
  });
}

/** W3C `traceparent` / `tracestate` for the active context (empty if none). */
export function traceHeaders(): Record<string, string> {
  const carrier: Record<string, string> = {};
  propagation.inject(context.active(), carrier);
  return carrier;
}
