// MCP server entry point. Serves health + metrics endpoints and the MCP
// protocol over stdio + Streamable HTTP (`/mcp`). When
// OPENCG__MCP__OAUTH_PASSWORD is set, it also mounts the SDK's OAuth router so
// OAuth-only clients (claude.ai) can connect — see src/oauth.ts (a temporary
// stopgap).
//
// stdout is the MCP stdio channel: every log line goes to stderr.

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { loadConfig } from "./config.js";
import { createHttpApp } from "./http-app.js";
import { PipelineClient } from "./pipeline-client.js";
import { buildMcpServer } from "./server.js";
import { initTelemetry, shutdownTelemetry } from "./telemetry.js";

async function main() {
  // Before anything else, so every transport's tool calls are traced.
  initTelemetry();
  for (const signal of ["SIGTERM", "SIGINT"] as const) {
    process.once(signal, () => {
      void shutdownTelemetry().finally(() => process.exit(0));
    });
  }

  const config = loadConfig();
  const pipeline = new PipelineClient(config.pipelineUrl);
  const ctx = { config, pipeline };

  const app = createHttpApp(ctx);
  const oauthEnabled = Boolean(config.oauthPassword);

  app.listen(config.port, () => {
    // eslint-disable-next-line no-console
    console.error(
      `[mcp-server] http listening on :${config.port} (mcp at /mcp, metrics at /metrics)`,
    );
    if (oauthEnabled) {
      // eslint-disable-next-line no-console
      console.error(
        `[mcp-server] OAuth stopgap ENABLED — shared-password gate at /authorize, metadata under ${config.publicUrl}`,
      );
    } else if (!config.httpToken) {
      // eslint-disable-next-line no-console
      console.error(
        "[mcp-server] WARNING: HTTP /mcp transport is UNAUTHENTICATED — set OPENCG__MCP__HTTP_TOKEN (or OPENCG__MCP__OAUTH_PASSWORD) before exposing this port.",
      );
    }
  });

  // ----- MCP server over stdio (always on) ---------------------------------
  const server = buildMcpServer(ctx);
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // eslint-disable-next-line no-console
  console.error("[mcp-server] mcp stdio transport connected");
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("[mcp-server] fatal:", err);
  process.exit(1);
});
