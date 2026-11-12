// Prometheus metrics for the MCP server, on a private registry. Default Node
// process metrics are deliberately not collected (design D5), so `/metrics`
// only shows `opencg_*` series. Label values are bounded: `tool` is one of the
// advertised tool names (or `unknown`), `outcome` is ok | error | rejected.

import type { NextFunction, Request, Response } from "express";
import { Counter, Histogram, Registry } from "@prometheus-io/client";

export type Outcome = "ok" | "error" | "rejected";

export const registry = new Registry();

export const requestsTotal = new Counter({
  name: "opencg_requests_total",
  help: "MCP/pipeline requests by tool and outcome (ok, error, rejected).",
  labelNames: ["tool", "outcome"] as const,
  registers: [registry],
});

// Same buckets as `opencg_shared.metrics.STAGE_LATENCY`.
export const stageLatencySeconds = new Histogram({
  name: "opencg_stage_latency_seconds",
  help: "Per-stage latency in seconds.",
  labelNames: ["stage"] as const,
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
  registers: [registry],
});

export function recordToolCall(tool: string, outcome: Outcome, seconds: number): void {
  requestsTotal.inc({ tool, outcome });
  stageLatencySeconds.observe({ stage: "mcp" }, seconds);
}

/** Express handler for the unauthenticated `GET /metrics`. */
export async function metricsHandler(_req: Request, res: Response): Promise<void> {
  res.setHeader("content-type", registry.contentType);
  res.send(await registry.metrics());
}

/**
 * Counts `/mcp` requests turned away by either auth gate (static bearer or
 * OAuth) as `rejected`. The tool is not known before auth, hence `unknown`.
 */
export function countAuthRejections(_req: Request, res: Response, next: NextFunction): void {
  res.on("finish", () => {
    if (res.statusCode === 401 || res.statusCode === 403) {
      requestsTotal.inc({ tool: "unknown", outcome: "rejected" });
    }
  });
  next();
}
