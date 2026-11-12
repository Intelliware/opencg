import type {
  RetrievalRequest,
  RetrievalResponse,
  TraverseRequest,
  TraverseResponse,
} from "@opencg/shared";
import { request as undiciRequest } from "undici";
import { traceHeaders } from "./telemetry.js";

export class PipelineRequestError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly responseBody: string,
  ) {
    super(`pipeline ${statusCode}: ${responseBody}`);
  }
}

// Every outgoing request carries the W3C `traceparent` / `tracestate` of the
// active span (the `mcp.<tool>` span during a tool call), so the pipeline
// continues the same trace.
export class PipelineClient {
  constructor(private readonly baseUrl: string) {}

  async retrieve(req: RetrievalRequest): Promise<RetrievalResponse> {
    const url = `${this.baseUrl.replace(/\/$/, "")}/retrieve`;
    const res = await undiciRequest(url, {
      method: "POST",
      headers: {
        ...traceHeaders(),
        "content-type": "application/json",
        "x-correlation-id": req.correlation_id,
      },
      body: JSON.stringify(req),
    });
    if (res.statusCode >= 400) {
      const body = await res.body.text();
      throw new PipelineRequestError(res.statusCode, body);
    }
    return (await res.body.json()) as RetrievalResponse;
  }

  async traverse(req: TraverseRequest, correlationId?: string): Promise<TraverseResponse> {
    const url = new URL(`${this.baseUrl.replace(/\/$/, "")}/graph/traverse`);
    url.searchParams.set("concept_id", req.concept_id);
    if (req.types?.length) {
      url.searchParams.set("types", req.types.join(","));
    }
    if (req.depth !== undefined) {
      url.searchParams.set("depth", String(req.depth));
    }
    if (req.limit !== undefined) {
      url.searchParams.set("limit", String(req.limit));
    }
    if (req.include_candidates !== undefined) {
      url.searchParams.set("include_candidates", String(req.include_candidates));
    }
    const headers: Record<string, string> = traceHeaders();
    if (correlationId) headers["x-correlation-id"] = correlationId;
    const res = await undiciRequest(url, { headers });
    if (res.statusCode >= 400) {
      const body = await res.body.text();
      throw new PipelineRequestError(res.statusCode, body);
    }
    return (await res.body.json()) as TraverseResponse;
  }

  async health(): Promise<boolean> {
    try {
      const res = await undiciRequest(`${this.baseUrl.replace(/\/$/, "")}/healthz`, {
        headers: traceHeaders(),
      });
      return res.statusCode === 200;
    } catch {
      return false;
    }
  }
}
