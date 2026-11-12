// HTTP surface of the MCP server: health endpoints, the unauthenticated
// Prometheus `/metrics`, and the MCP protocol at `/mcp` behind either the
// static bearer gate or the stopgap OAuth router (see src/oauth.ts).

import express, { type Express } from "express";
import { requireBearerAuth } from "@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js";
import {
  getOAuthProtectedResourceMetadataUrl,
  mcpAuthRouter,
} from "@modelcontextprotocol/sdk/server/auth/router.js";
import { countAuthRejections, metricsHandler } from "./metrics.js";
import { createStopgapOAuth } from "./oauth.js";
import { dispatchMcp, handleMcpHttp } from "./server.js";
import type { ToolCallContext } from "./tools.js";

export function createHttpApp(ctx: ToolCallContext): Express {
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

  app.use("/mcp", countAuthRejections);

  if (config.oauthPassword) {
    const { provider, approveHandler } = createStopgapOAuth({
      password: config.oauthPassword,
      staticToken: config.httpToken,
    });
    const issuerUrl = new URL(config.publicUrl);
    app.use(mcpAuthRouter({ provider, issuerUrl, resourceName: "openCG MCP" }));
    app.post("/oauth/approve", express.urlencoded({ extended: false }), approveHandler);
    const resourceMetadataUrl = getOAuthProtectedResourceMetadataUrl(issuerUrl);
    app.all(
      "/mcp",
      requireBearerAuth({ verifier: provider, resourceMetadataUrl }),
      (req, res) => {
        void dispatchMcp(req, res, ctx);
      },
    );
  } else {
    // OAuth disabled: static-bearer gate (or open) — unchanged behaviour.
    app.all("/mcp", (req, res) => {
      void handleMcpHttp(req, res, ctx);
    });
  }

  return app;
}
