// Auth settings for the admin UI, read from the same OPENCG__AUTH__* variables
// as every other openCG service (design D1, D3, D6).

export type AuthMode = "none" | "oidc";

type Env = Record<string, string | undefined>;

const MODES: readonly AuthMode[] = ["none", "oidc"];
const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost"]);
const REMOVED_STOPGAPS = ["OPENCG__ADMIN_UI__PASSWORD", "OPENCG__MCP__OAUTH_PASSWORD"] as const;
const MIGRATION_DOC = "the migration section of docs/OPERATIONS.md";

function value(env: Env, key: string): string | undefined {
  const raw = env[key];
  if (raw === undefined) return undefined;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/** `OPENCG__AUTH__MODE`, default `none`. Throws on an unknown value. */
export function authMode(env: Env = process.env): AuthMode {
  const mode = value(env, "OPENCG__AUTH__MODE") ?? "none";
  if (!(MODES as readonly string[]).includes(mode)) {
    throw new Error(`OPENCG__AUTH__MODE must be "oidc" or "none", got "${mode}"`);
  }
  return mode as AuthMode;
}

export interface OidcSettings {
  /** Public issuer: checked against `iss`, base of browser redirects. */
  issuer: string;
  /** Where server-side code reaches the issuer (discovery, token, JWKS). */
  internalUrl: string;
  audience: string;
  principalClaim: string;
  rolesClaim: string;
  clientId: string;
  clientSecret?: string;
  /** The admin UI's own public origin, e.g. http://localhost:3300. */
  publicUrl: string;
  scope: string;
}

function stripSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export function oidcSettings(env: Env = process.env): OidcSettings {
  const issuer = stripSlash(value(env, "OPENCG__AUTH__OIDC__ISSUER") ?? "");
  return {
    issuer,
    internalUrl: stripSlash(value(env, "OPENCG__AUTH__OIDC__INTERNAL_URL") ?? issuer),
    audience: value(env, "OPENCG__AUTH__OIDC__AUDIENCE") ?? "opencg",
    principalClaim: value(env, "OPENCG__AUTH__OIDC__PRINCIPAL_CLAIM") ?? "preferred_username",
    rolesClaim: value(env, "OPENCG__AUTH__OIDC__ROLES_CLAIM") ?? "roles",
    clientId: value(env, "OPENCG__ADMIN_UI__OIDC__CLIENT_ID") ?? "opencg-admin-ui",
    clientSecret: value(env, "OPENCG__ADMIN_UI__OIDC__CLIENT_SECRET"),
    publicUrl: stripSlash(value(env, "OPENCG__ADMIN_UI__PUBLIC_URL") ?? "http://localhost:3000"),
    scope: "openid profile email",
  };
}

export function valkeyUrl(env: Env = process.env): string {
  return value(env, "OPENCG__VALKEY__URL") ?? "redis://valkey:6379/0";
}

/** The redirect URI registered with the IdP. */
export function callbackUrl(settings: OidcSettings): string {
  return `${settings.publicUrl}/api/auth/callback`;
}

/**
 * Configuration the admin UI refuses to start with (design D1, D12). Each
 * message names the offending variable.
 */
export function startupProblems(env: Env = process.env): string[] {
  const problems: string[] = [];
  for (const key of REMOVED_STOPGAPS) {
    if (value(env, key) !== undefined) {
      problems.push(
        `${key} is set, but the shared-password stopgap was removed. Unset it and follow the ` +
          `steps in ${MIGRATION_DOC}.`,
      );
    }
  }
  let mode: AuthMode;
  try {
    mode = authMode(env);
  } catch (error) {
    problems.push((error as Error).message);
    return problems;
  }
  if (mode === "none") {
    const bind = value(env, "OPENCG__BIND_ADDRESS");
    if (bind !== undefined && !LOOPBACK.has(bind)) {
      problems.push(
        `OPENCG__AUTH__MODE=none with OPENCG__BIND_ADDRESS=${bind}: the unauthenticated admin UI ` +
          "may only bind to a loopback address. Use OPENCG__AUTH__MODE=oidc or a loopback bind.",
      );
    }
    return problems;
  }
  if (value(env, "OPENCG__AUTH__OIDC__ISSUER") === undefined) {
    problems.push("OPENCG__AUTH__MODE=oidc requires OPENCG__AUTH__OIDC__ISSUER.");
  }
  if (env.OPENCG__AUTH__OIDC__AUDIENCE !== undefined && value(env, "OPENCG__AUTH__OIDC__AUDIENCE") === undefined) {
    problems.push("OPENCG__AUTH__MODE=oidc requires a non-empty OPENCG__AUTH__OIDC__AUDIENCE.");
  }
  if (value(env, "OPENCG__ADMIN_UI__OIDC__CLIENT_SECRET") === undefined) {
    problems.push("OPENCG__AUTH__MODE=oidc requires OPENCG__ADMIN_UI__OIDC__CLIENT_SECRET.");
  }
  if (value(env, "OPENCG__ADMIN_UI__PUBLIC_URL") === undefined) {
    problems.push("OPENCG__AUTH__MODE=oidc requires OPENCG__ADMIN_UI__PUBLIC_URL (the callback base).");
  }
  return problems;
}
