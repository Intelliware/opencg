// Caller authentication for the MCP server (add-identity-and-opa, design D1,
// D1a, D4, D5, D6). One `Authenticator` turns an `Authorization` header value
// into either a `Caller` or a failure reason, for both transports:
//
//   * `ock_…` bearer      → named API key (only when OPENCG__ENVIRONMENT=dev,
//                           otherwise `api_key_disabled`)
//   * legacy HTTP token   → API key `mcp-http-token` with the stub identity (dev only)
//   * anything else, oidc → a JWT verified against the issuer's JWKS with `jose`
//   * none mode, no token → the stub identity (open), unless a key or the HTTP
//                           token is configured, in which case one is required
//
// Tokens are never logged. Every failure increments
// `opencg_auth_failures_total{service="mcp-server",reason}`.

import { createHash, timingSafeEqual } from "node:crypto";
import { createRemoteJWKSet, errors, type JWTPayload, jwtVerify } from "jose";
import type { ApiKeyEntry, McpConfig, OidcConfig } from "./config.js";
import { authFailuresTotal } from "./metrics.js";

export type AuthMethod = "oidc" | "none" | "api_key";

export type AuthFailureReason =
  | "token_missing"
  | "token_expired"
  | "token_invalid"
  | "issuer_unreachable"
  | "api_key_disabled";

export interface Caller {
  principal: string;
  roles: string[];
  tenant: string;
  authMethod: AuthMethod;
  /** API key name when `authMethod = "api_key"`. */
  keyName?: string;
  /**
   * The exact `Authorization` header value to forward to the pipeline, or
   * null when the pipeline should use its stub identity (`none` mode, no token).
   */
  authorization: string | null;
}

export type AuthResult =
  | { ok: true; caller: Caller }
  | { ok: false; reason: AuthFailureReason; tokenPresent: boolean };

export const API_KEY_PREFIX = "ock_";
export const LEGACY_KEY_NAME = "mcp-http-token";
export const ALLOWED_ALGORITHMS = ["RS256", "ES256"];
export const CLOCK_TOLERANCE_SECONDS = 60;
export const JWKS_COOLDOWN_MS = 30_000;

/** Lowercase hex SHA-256 of the full raw key (prefix included), as stored in the keys file. */
export function hashApiKey(rawKey: string): string {
  return createHash("sha256").update(rawKey, "utf8").digest("hex");
}

function digestEqual(a: Buffer, b: Buffer): boolean {
  return a.length === b.length && timingSafeEqual(a, b);
}

/** Constant-time string equality via SHA-256 digests (length-independent). */
function constantTimeEqual(a: string, b: string): boolean {
  return digestEqual(
    createHash("sha256").update(a, "utf8").digest(),
    createHash("sha256").update(b, "utf8").digest(),
  );
}

/** `realm_access.roles` → `claims.realm_access.roles`; a missing path or non-array → []. */
export function readRoles(claims: JWTPayload, path: string): string[] {
  let node: unknown = claims;
  for (const part of path.split(".")) {
    if (node === null || typeof node !== "object") return [];
    node = (node as Record<string, unknown>)[part];
  }
  return Array.isArray(node) ? node.filter((r): r is string => typeof r === "string") : [];
}

export function mapClaims(
  claims: JWTPayload,
  oidc: OidcConfig,
  defaultTenant: string,
): { principal: string; roles: string[]; tenant: string } | null {
  const named = claims[oidc.principalClaim];
  const principal =
    typeof named === "string" && named ? named : typeof claims.sub === "string" ? claims.sub : "";
  if (!principal) return null;
  const tenantValue = oidc.tenantClaim ? claims[oidc.tenantClaim] : undefined;
  return {
    principal,
    roles: readRoles(claims, oidc.rolesClaim),
    tenant: typeof tenantValue === "string" && tenantValue ? tenantValue : defaultTenant,
  };
}

class IssuerUnreachable extends Error {}

type KeyResolver = Parameters<typeof jwtVerify>[1];

/**
 * Fetches `${INTERNAL_URL or ISSUER}/.well-known/openid-configuration` once,
 * then verifies against its `jwks_uri` through jose's cached remote JWKS
 * (refetched on an unknown `kid`, at most once every 30 s). When an internal
 * URL is set, the `jwks_uri` origin is rewritten to it: Keycloak puts its
 * public hostname there, which containers cannot reach.
 */
export class OidcVerifier {
  private jwks: ReturnType<typeof createRemoteJWKSet> | null = null;
  private discovery: Promise<ReturnType<typeof createRemoteJWKSet>> | null = null;

  constructor(
    private readonly oidc: OidcConfig,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  private discover(): Promise<ReturnType<typeof createRemoteJWKSet>> {
    if (this.jwks) return Promise.resolve(this.jwks);
    if (!this.discovery) {
      this.discovery = (async () => {
        const base = (this.oidc.internalUrl ?? this.oidc.issuer).replace(/\/+$/, "");
        let jwksUri: URL;
        try {
          const res = await this.fetchImpl(`${base}/.well-known/openid-configuration`, {
            signal: AbortSignal.timeout(5000),
          });
          if (!res.ok) throw new Error(`discovery HTTP ${res.status}`);
          const doc = (await res.json()) as { jwks_uri?: unknown };
          if (typeof doc.jwks_uri !== "string") throw new Error("discovery has no jwks_uri");
          jwksUri = new URL(doc.jwks_uri);
        } catch (err) {
          throw new IssuerUnreachable(err instanceof Error ? err.message : String(err));
        }
        if (this.oidc.internalUrl) {
          const internal = new URL(this.oidc.internalUrl);
          jwksUri.protocol = internal.protocol;
          jwksUri.host = internal.host;
        }
        this.jwks = createRemoteJWKSet(jwksUri, {
          cooldownDuration: JWKS_COOLDOWN_MS,
          timeoutDuration: 5000,
        });
        return this.jwks;
      })().finally(() => {
        // Failed discovery is retried on the next token; success is cached in `jwks`.
        this.discovery = null;
      });
    }
    return this.discovery;
  }

  async verify(token: string): Promise<JWTPayload> {
    const keys: KeyResolver = async (header, input) => (await this.discover())(header, input);
    const { payload } = await jwtVerify(token, keys, {
      issuer: this.oidc.issuer,
      audience: this.oidc.audience,
      algorithms: ALLOWED_ALGORITHMS,
      clockTolerance: CLOCK_TOLERANCE_SECONDS,
      requiredClaims: ["exp", "iss", "aud"],
    });
    return payload;
  }
}

export function classifyVerifyError(err: unknown): AuthFailureReason {
  if (err instanceof IssuerUnreachable) return "issuer_unreachable";
  if (err instanceof errors.JWTExpired) return "token_expired";
  if (err instanceof errors.JWKSTimeout) return "issuer_unreachable";
  if (err instanceof errors.JOSEError) {
    // jose's remote JWKS raises the generic class for a non-200 or unparseable
    // JWKS response; every specific validation failure has its own subclass.
    return err.code === "ERR_JOSE_GENERIC" ? "issuer_unreachable" : "token_invalid";
  }
  // Network errors from fetching the JWKS surface as plain errors.
  return err instanceof TypeError || (err as { name?: string })?.name === "AbortError"
    ? "issuer_unreachable"
    : "token_invalid";
}

export class Authenticator {
  private readonly verifier: OidcVerifier | null;
  private readonly keyDigests: { entry: ApiKeyEntry; digest: Buffer }[];

  constructor(
    private readonly config: McpConfig,
    opts: { fetchImpl?: typeof fetch } = {},
  ) {
    this.verifier = config.oidc ? new OidcVerifier(config.oidc, opts.fetchImpl) : null;
    this.keyDigests = config.apiKeys.map((entry) => ({
      entry,
      digest: Buffer.from(entry.key_sha256, "hex"),
    }));
  }

  /** True when `/mcp` is served without any credential (none mode, no key, no token). */
  get open(): boolean {
    return (
      this.config.authMode === "none" && this.config.apiKeys.length === 0 && !this.config.httpToken
    );
  }

  /** The stub identity: `none` mode with no credential. */
  stubCaller(): Caller {
    return {
      principal: this.config.identity.principal,
      roles: [...this.config.identity.roles],
      tenant: this.config.tenant,
      authMethod: "none",
      authorization: null,
    };
  }

  async authenticate(authorization: string | undefined | null): Promise<AuthResult> {
    const result = await this.authenticateInner((authorization ?? "").trim());
    if (!result.ok) authFailuresTotal.inc({ service: "mcp-server", reason: result.reason });
    return result;
  }

  private async authenticateInner(header: string): Promise<AuthResult> {
    // Like the Python verifier: a non-Bearer scheme counts as no token.
    const token = /^Bearer\s+(\S+)$/i.exec(header)?.[1];
    if (!token) {
      if (this.open) return { ok: true, caller: this.stubCaller() };
      return { ok: false, reason: "token_missing", tokenPresent: false };
    }

    if (token.startsWith(API_KEY_PREFIX)) return this.apiKey(token, header);

    if (
      this.config.environment === "dev" &&
      this.config.httpToken &&
      constantTimeEqual(token, this.config.httpToken)
    ) {
      return {
        ok: true,
        caller: {
          ...this.stubCaller(),
          authMethod: "api_key",
          keyName: LEGACY_KEY_NAME,
          authorization: header,
        },
      };
    }

    if (this.verifier && this.config.oidc) {
      try {
        const claims = await this.verifier.verify(token);
        const mapped = mapClaims(claims, this.config.oidc, this.config.tenant);
        if (!mapped) return { ok: false, reason: "token_invalid", tokenPresent: true };
        return { ok: true, caller: { ...mapped, authMethod: "oidc", authorization: header } };
      } catch (err) {
        return { ok: false, reason: classifyVerifyError(err), tokenPresent: true };
      }
    }

    // none mode: an open server ignores an unrecognised bearer (as before);
    // a gated one rejects it.
    if (this.open) return { ok: true, caller: this.stubCaller() };
    return { ok: false, reason: "token_invalid", tokenPresent: true };
  }

  private apiKey(token: string, header: string): AuthResult {
    if (this.config.environment !== "dev") {
      return { ok: false, reason: "api_key_disabled", tokenPresent: true };
    }
    const digest = createHash("sha256").update(token, "utf8").digest();
    let found: ApiKeyEntry | null = null;
    // Compare against every entry so timing does not reveal which one matched.
    for (const { entry, digest: expected } of this.keyDigests) {
      if (digestEqual(digest, expected) && !found) found = entry;
    }
    if (!found) return { ok: false, reason: "token_invalid", tokenPresent: true };
    return {
      ok: true,
      caller: {
        principal: found.principal,
        roles: [...found.roles],
        tenant: this.config.tenant,
        authMethod: "api_key",
        keyName: found.name,
        authorization: header,
      },
    };
  }
}
