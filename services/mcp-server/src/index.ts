// MCP server entry point. Serves health + metrics endpoints and the MCP
// protocol over stdio + Streamable HTTP (`/mcp`). Authentication follows
// OPENCG__AUTH__MODE (`none` | `oidc`) and OPENCG__ENVIRONMENT (API keys only
// in `dev`); see src/config.ts and src/auth.ts. Unsafe configuration exits
// non-zero before anything listens.
//
// stdout is the MCP stdio channel: every log line goes to stderr.

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Authenticator } from "./auth.js";
import { ConfigError, loadConfig, type McpConfig } from "./config.js";
import { createHttpApp } from "./http-app.js";
import { PipelineClient } from "./pipeline-client.js";
import { buildMcpServer, type McpServerContext } from "./server.js";
import { initTelemetry, shutdownTelemetry } from "./telemetry.js";

function log(message: string): void {
  // eslint-disable-next-line no-console
  console.error(`[mcp-server] ${message}`);
}

function loadConfigOrExit(): McpConfig {
  try {
    return loadConfig();
  } catch (err) {
    if (err instanceof ConfigError) {
      log(`refusing to start: ${err.message}`);
      process.exit(2);
    }
    throw err;
  }
}

async function main() {
  // Config first: an unsafe configuration must stop the process before any
  // listener or exporter starts.
  const config = loadConfigOrExit();

  // Before anything else, so every transport's tool calls are traced.
  initTelemetry();
  for (const signal of ["SIGTERM", "SIGINT"] as const) {
    process.once(signal, () => {
      void shutdownTelemetry().finally(() => process.exit(0));
    });
  }

  const pipeline = new PipelineClient(config.pipelineUrl);
  const authenticator = new Authenticator(config);
  const app = createHttpApp({ config, pipeline, authenticator });

  app.listen(config.port, () => {
    log(`http listening on :${config.port} (mcp at /mcp, metrics at /metrics)`);
    log(`auth mode ${config.authMode}, environment ${config.environment}`);
    if (config.authMode === "oidc") {
      log(
        `OIDC resource server: issuer ${config.oidc?.issuer}, metadata at ${config.publicUrl}/.well-known/oauth-protected-resource`,
      );
    } else if (authenticator.open) {
      log(
        "WARNING: running without authentication (OPENCG__AUTH__MODE=none) — HTTP /mcp transport is UNAUTHENTICATED; keep it on loopback or set OPENCG__AUTH__MODE=oidc.",
      );
    } else {
      log("WARNING: OPENCG__AUTH__MODE=none; /mcp accepts dev API keys only.");
    }
    if (config.environment === "dev" && (config.apiKeys.length > 0 || config.httpToken)) {
      log(
        `dev API keys enabled (${config.apiKeys.length} named${config.httpToken ? " + legacy mcp-http-token" : ""})`,
      );
    }
  });

  // ----- MCP server over stdio (always on) ---------------------------------
  const stdioCtx: McpServerContext = { config, pipeline };
  if (config.authMode === "oidc") {
    // Verified per tool call; a missing or invalid token fails each call with
    // `unauthenticated` while initialize and tools/list keep working.
    const header = config.stdioToken ? `Bearer ${config.stdioToken}` : undefined;
    stdioCtx.resolveCaller = () => authenticator.authenticate(header);
    if (!config.stdioToken) {
      log("OPENCG__MCP__STDIO_TOKEN is not set: stdio tool calls will fail with unauthenticated");
    }
  }
  const server = buildMcpServer(stdioCtx);
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("mcp stdio transport connected");
}

main().catch((err) => {
  log(`fatal: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
