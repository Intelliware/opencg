// Env-only config loader for the TS MCP server (the source of truth is
// opencg.yaml consumed by the Python services; the MCP server reads the same
// variables). `loadConfig` also runs the startup safety checks of
// add-identity-and-opa (design D1, D1a, D12): any unsafe combination throws a
// `ConfigError` naming the variable, and `index.ts` exits non-zero with it.

import { readFileSync } from "node:fs";

export type AuthMode = "none" | "oidc";
export type Environment = "dev" | "test" | "staging" | "production";

export interface OidcConfig {
  /** Public issuer, checked against `iss` and advertised in resource metadata. */
  issuer: string;
  /** Where discovery and JWKS are fetched from; defaults to the issuer. */
  internalUrl: string | null;
  audience: string;
  principalClaim: string;
  /** Dotted path, e.g. `roles` or `realm_access.roles`. */
  rolesClaim: string;
  /** Empty → the configured tenant. */
  tenantClaim: string | null;
}

export interface ApiKeyEntry {
  name: string;
  /** Lowercase hex SHA-256 of the full raw key, including its `ock_` prefix. */
  key_sha256: string;
  principal: string;
  roles: string[];
}

export interface McpConfig {
  tenant: string;
  /** Stub identity: used in `none` mode and for the legacy HTTP token. */
  identity: { principal: string; roles: string[] };
  pipelineUrl: string;
  port: number;
  /** Public base URL (e.g. the ngrok HTTPS URL), used in resource metadata. */
  publicUrl: string;
  environment: Environment;
  authMode: AuthMode;
  /** Set only in `oidc` mode. */
  oidc: OidcConfig | null;
  /** Named API keys (accepted only in `dev`). */
  apiKeys: ApiKeyEntry[];
  /** Legacy dev-only API key `mcp-http-token`. null = not configured. */
  httpToken: string | null;
  /** Bearer credential for the stdio transport in `oidc` mode. */
  stdioToken: string | null;
}

export const MIGRATION_DOC = "the migration section of docs/OPERATIONS.md";

export class ConfigError extends Error {}

const ENVIRONMENTS: readonly Environment[] = ["dev", "test", "staging", "production"];
const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost", "[::1]"]);

type Env = NodeJS.ProcessEnv;

function str(env: Env, name: string): string {
  return (env[name] ?? "").trim();
}

function withDefault(env: Env, name: string, fallback: string): string {
  return str(env, name) || fallback;
}

function csv(value: string): string[] {
  return value
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean);
}

/** Parse an `OPENCG__AUTH__API_KEYS_FILE` JSON array of `{name, key_sha256, principal, roles}`. */
export function parseApiKeys(raw: string, source = "OPENCG__AUTH__API_KEYS_FILE"): ApiKeyEntry[] {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new ConfigError(`${source}: not valid JSON`);
  }
  if (!Array.isArray(data)) throw new ConfigError(`${source}: expected a JSON array`);
  return data.map((item: unknown, i) => {
    const e = (item ?? {}) as Record<string, unknown>;
    const name = typeof e.name === "string" ? e.name.trim() : "";
    const hash = typeof e.key_sha256 === "string" ? e.key_sha256.trim().toLowerCase() : "";
    const principal = typeof e.principal === "string" ? e.principal.trim() : "";
    const roles = Array.isArray(e.roles) ? e.roles.filter((r): r is string => typeof r === "string") : null;
    if (!name || !principal || roles === null || !/^[0-9a-f]{64}$/.test(hash)) {
      throw new ConfigError(
        `${source}: entry ${i} must have name, principal, roles[] and a 64-hex key_sha256`,
      );
    }
    return { name, key_sha256: hash, principal, roles };
  });
}

export function loadConfig(env: Env = process.env): McpConfig {
  // D12: removed stopgap settings must not silently turn a deployment open.
  if (str(env, "OPENCG__MCP__OAUTH_PASSWORD")) {
    throw new ConfigError(
      `OPENCG__MCP__OAUTH_PASSWORD is set, but the stopgap shared-password OAuth gate was removed. ` +
        `Unset it and configure OPENCG__AUTH__MODE=oidc with your IdP; see ${MIGRATION_DOC}.`,
    );
  }

  const rawMode = withDefault(env, "OPENCG__AUTH__MODE", "none");
  if (rawMode !== "none" && rawMode !== "oidc") {
    throw new ConfigError(`OPENCG__AUTH__MODE must be "none" or "oidc", got "${rawMode}"`);
  }
  const authMode: AuthMode = rawMode;

  const rawEnv = withDefault(env, "OPENCG__ENVIRONMENT", "production");
  if (!(ENVIRONMENTS as readonly string[]).includes(rawEnv)) {
    throw new ConfigError(
      `OPENCG__ENVIRONMENT must be one of ${ENVIRONMENTS.join(", ")}, got "${rawEnv}"`,
    );
  }
  const environment = rawEnv as Environment;

  const bindAddress = str(env, "OPENCG__BIND_ADDRESS");
  if (authMode === "none" && bindAddress && !LOOPBACK.has(bindAddress.toLowerCase())) {
    throw new ConfigError(
      `OPENCG__AUTH__MODE=none with OPENCG__BIND_ADDRESS=${bindAddress} would expose an ` +
        `unauthenticated server; bind to loopback or set OPENCG__AUTH__MODE=oidc`,
    );
  }

  let oidc: OidcConfig | null = null;
  if (authMode === "oidc") {
    const issuer = str(env, "OPENCG__AUTH__OIDC__ISSUER");
    if (!issuer) throw new ConfigError("OPENCG__AUTH__MODE=oidc requires OPENCG__AUTH__OIDC__ISSUER");
    // AUDIENCE defaults to `opencg` only when unset; set-but-empty is refused.
    const audience =
      env.OPENCG__AUTH__OIDC__AUDIENCE === undefined ? "opencg" : str(env, "OPENCG__AUTH__OIDC__AUDIENCE");
    if (!audience) throw new ConfigError("OPENCG__AUTH__MODE=oidc requires OPENCG__AUTH__OIDC__AUDIENCE");
    oidc = {
      issuer,
      internalUrl: str(env, "OPENCG__AUTH__OIDC__INTERNAL_URL") || null,
      audience,
      principalClaim: withDefault(env, "OPENCG__AUTH__OIDC__PRINCIPAL_CLAIM", "preferred_username"),
      rolesClaim: withDefault(env, "OPENCG__AUTH__OIDC__ROLES_CLAIM", "roles"),
      tenantClaim: str(env, "OPENCG__AUTH__OIDC__TENANT_CLAIM") || null,
    };
  }

  // D1a: API keys and the legacy HTTP token exist only in `dev`.
  const keysFile = str(env, "OPENCG__AUTH__API_KEYS_FILE");
  let apiKeys: ApiKeyEntry[] = [];
  if (keysFile) {
    if (environment !== "dev") {
      throw new ConfigError(
        `OPENCG__AUTH__API_KEYS_FILE is set but API keys are allowed only when OPENCG__ENVIRONMENT=dev ` +
          `(current: ${environment}); unset it or use the IdP's client-credentials grant`,
      );
    }
    let raw: string;
    try {
      raw = readFileSync(keysFile, "utf8");
    } catch {
      throw new ConfigError(`OPENCG__AUTH__API_KEYS_FILE: cannot read ${keysFile}`);
    }
    apiKeys = parseApiKeys(raw);
  }
  const httpToken = str(env, "OPENCG__MCP__HTTP_TOKEN") || null;
  if (httpToken && environment !== "dev") {
    throw new ConfigError(
      `OPENCG__MCP__HTTP_TOKEN is set but it is accepted only when OPENCG__ENVIRONMENT=dev ` +
        `(current: ${environment}); unset it and use the IdP's client-credentials grant, see ${MIGRATION_DOC}`,
    );
  }

  const port = withDefault(env, "OPENCG__MCP__PORT", "8080");
  return {
    tenant: withDefault(env, "OPENCG__TENANT", "default"),
    identity: {
      principal: withDefault(env, "OPENCG__IDENTITY__PRINCIPAL", "local-dev"),
      roles: csv(withDefault(env, "OPENCG__IDENTITY__ROLES", "admin,reader")),
    },
    pipelineUrl: withDefault(env, "OPENCG__PIPELINE__URL", "http://pipeline:8000"),
    port: Number(port),
    publicUrl: (str(env, "OPENCG__MCP__PUBLIC_URL") || `http://localhost:${port}`).replace(/\/+$/, ""),
    environment,
    authMode,
    oidc,
    apiKeys,
    httpToken,
    stdioToken: str(env, "OPENCG__MCP__STDIO_TOKEN") || null,
  };
}
