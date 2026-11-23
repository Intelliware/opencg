// HTTP surface of the MCP server: health endpoints, the unauthenticated
// Prometheus `/metrics`, the OAuth protected-resource metadata (oidc mode), and
// the MCP protocol at `/mcp` behind the caller authenticator (src/auth.ts).
//
// The MCP server is an OAuth resource server only (design D4): it serves no
// `/authorize`, `/token`, `/register`, `/revoke` or authorization-server
// metadata, so those paths fall through to Express's 404.

import express, { type Express, type Request, type Response } from "express";
import { countAuthRejections, metricsHandler } from "./metrics.js";
import { type HttpContext, handleMcpHttp } from "./server.js";

/** RFC 9728 protected-resource metadata for `oidc` mode. */
export function protectedResourceMetadata(ctx: HttpContext): Record<string, unknown> {
  const { publicUrl, oidc } = ctx.config;
  return {
    resource: `${publicUrl}/mcp`,
    authorization_servers: oidc ? [oidc.issuer] : [],
    bearer_methods_supported: ["header"],
    scopes_supported: ["openid"],
  };
}

export function createHttpApp(ctx: HttpContext): Express {
  const { config, pipeline } = ctx;
  const app = express();
  app.disable("x-powered-by");

  app.get("/healthz", (_req, res) => {
    res.json({ status: "ok" });
  });
  app.get("/readyz", async (_req, res) => {
    const ok = await pipeline.health();
    res.status(ok ? 200 : 503).json({ status: ok ? "ready" : "pipeline_unavailable" });
  });
  // Unauthenticated by design, like the health endpoints: labels are bounded
  // and carry no query text, principals or IDs.
  app.get("/metrics", (req, res) => {
    void metricsHandler(req, res);
  });

  if (config.authMode === "oidc") {
    const metadata = (_req: Request, res: Response) => {
      res.json(protectedResourceMetadata(ctx));
    };
    // Bare and path-suffixed (`/mcp`) forms: clients probe either.
    app.get("/.well-known/oauth-protected-resource", metadata);
    app.get("/.well-known/oauth-protected-resource/mcp", metadata);
  }

  app.use("/mcp", countAuthRejections);
  app.all("/mcp", (req, res) => {
    void handleMcpHttp(req, res, ctx);
  });

  return app;
}
