import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SignJWT, UnsecuredJWT } from "jose";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Authenticator, hashApiKey, mapClaims, readRoles } from "./auth.js";
import { ConfigError, loadConfig } from "./config.js";
import { authFailuresTotal } from "./metrics.js";
import { startTestIdp, type TestIdp } from "./test-idp.js";

function keysFile(entries: unknown): string {
  const dir = mkdtempSync(join(tmpdir(), "opencg-keys-"));
  const path = join(dir, "keys.json");
  writeFileSync(path, JSON.stringify(entries));
  return path;
}

const RAW_KEY = "ock_test_0123456789abcdef"; // gitleaks:allow (test fixture, not a credential)
const KEYS = [{ name: "ci-bot", key_sha256: hashApiKey(RAW_KEY), principal: "ci-bot", roles: ["reader"] }];

async function failures(reason: string): Promise<number> {
  const { values } = await authFailuresTotal.get();
  const v = values.find(
    (x) => (x.labels as Record<string, string>).reason === reason &&
      (x.labels as Record<string, string>).service === "mcp-server",
  );
  return v?.value ?? 0;
}

describe("loadConfig startup checks", () => {
  it("defaults to none mode and the production environment", () => {
    const c = loadConfig({});
    expect(c.authMode).toBe("none");
    expect(c.environment).toBe("production");
    expect(c.oidc).toBeNull();
  });

  it("refuses the removed OAuth password, naming it and the migration doc", () => {
    expect(() => loadConfig({ OPENCG__MCP__OAUTH_PASSWORD: "x" })).toThrow(
      /OPENCG__MCP__OAUTH_PASSWORD.*docs\/OPERATIONS\.md/s,
    );
  });

  it("refuses unknown mode and environment values", () => {
    expect(() => loadConfig({ OPENCG__AUTH__MODE: "basic" })).toThrow(/OPENCG__AUTH__MODE/);
    expect(() => loadConfig({ OPENCG__ENVIRONMENT: "prod" })).toThrow(/OPENCG__ENVIRONMENT/);
  });

  it("refuses oidc without an issuer or with an empty audience", () => {
    expect(() => loadConfig({ OPENCG__AUTH__MODE: "oidc" })).toThrow(/OPENCG__AUTH__OIDC__ISSUER/);
    expect(() =>
      loadConfig({
        OPENCG__AUTH__MODE: "oidc",
        OPENCG__AUTH__OIDC__ISSUER: "http://idp",
        OPENCG__AUTH__OIDC__AUDIENCE: "",
      }),
    ).toThrow(/OPENCG__AUTH__OIDC__AUDIENCE/);
  });

  it("applies the OIDC defaults", () => {
    const c = loadConfig({ OPENCG__AUTH__MODE: "oidc", OPENCG__AUTH__OIDC__ISSUER: "http://idp" });
    expect(c.oidc).toEqual({
      issuer: "http://idp",
      internalUrl: null,
      audience: "opencg",
      principalClaim: "preferred_username",
      rolesClaim: "roles",
      tenantClaim: null,
    });
  });

  it("refuses none mode on a non-loopback bind address, naming both variables", () => {
    expect(() => loadConfig({ OPENCG__BIND_ADDRESS: "0.0.0.0" })).toThrow(
      /OPENCG__AUTH__MODE=none.*OPENCG__BIND_ADDRESS/,
    );
    expect(() => loadConfig({ OPENCG__BIND_ADDRESS: "127.0.0.1" })).not.toThrow();
    expect(() =>
      loadConfig({
        OPENCG__BIND_ADDRESS: "0.0.0.0",
        OPENCG__AUTH__MODE: "oidc",
        OPENCG__AUTH__OIDC__ISSUER: "http://idp",
      }),
    ).not.toThrow();
  });

  it("refuses API keys and the HTTP token outside dev (unset environment = production)", () => {
    const file = keysFile(KEYS);
    expect(() => loadConfig({ OPENCG__AUTH__API_KEYS_FILE: file })).toThrow(ConfigError);
    expect(() =>
      loadConfig({ OPENCG__AUTH__API_KEYS_FILE: file, OPENCG__ENVIRONMENT: "staging" }),
    ).toThrow(/OPENCG__AUTH__API_KEYS_FILE/);
    expect(() =>
      loadConfig({ OPENCG__MCP__HTTP_TOKEN: "s3cret", OPENCG__ENVIRONMENT: "production" }),
    ).toThrow(/OPENCG__MCP__HTTP_TOKEN/);
    const dev = loadConfig({
      OPENCG__AUTH__API_KEYS_FILE: file,
      OPENCG__MCP__HTTP_TOKEN: "s3cret",
      OPENCG__ENVIRONMENT: "dev",
    });
    expect(dev.apiKeys).toHaveLength(1);
    expect(dev.httpToken).toBe("s3cret");
  });

  it("rejects a malformed keys file", () => {
    const file = keysFile([{ name: "x", key_sha256: "abc", principal: "p", roles: [] }]);
    expect(() => loadConfig({ OPENCG__AUTH__API_KEYS_FILE: file, OPENCG__ENVIRONMENT: "dev" })).toThrow(
      /key_sha256/,
    );
  });
});

describe("claim mapping", () => {
  const oidc = {
    issuer: "i",
    internalUrl: null,
    audience: "opencg",
    principalClaim: "preferred_username",
    rolesClaim: "realm_access.roles",
    tenantClaim: null,
  };
  it("falls back to sub, reads a dotted roles path, defaults the tenant", () => {
    expect(mapClaims({ sub: "8f2c", realm_access: { roles: ["reader", "legal", 3] } }, oidc, "default")).toEqual({
      principal: "8f2c",
      roles: ["reader", "legal"],
      tenant: "default",
    });
  });
  it("uses the tenant claim when configured", () => {
    expect(mapClaims({ preferred_username: "a", org: "acme" }, { ...oidc, tenantClaim: "org" }, "d")?.tenant).toBe(
      "acme",
    );
  });
  it("gives no roles for a missing path", () => {
    expect(readRoles({}, "roles")).toEqual([]);
    expect(readRoles({ roles: "admin" }, "roles")).toEqual([]);
  });
});

describe("Authenticator (oidc mode)", () => {
  let idp: TestIdp;
  let auth: Authenticator;

  beforeAll(async () => {
    // Discovery advertises a public issuer whose host the server cannot reach;
    // the internal URL must be used for discovery and for the JWKS origin.
    idp = await startTestIdp({ publicIssuer: "http://idp.public.invalid/realms/opencg" });
    auth = new Authenticator(
      loadConfig({
        OPENCG__AUTH__MODE: "oidc",
        OPENCG__AUTH__OIDC__ISSUER: "http://idp.public.invalid/realms/opencg",
        OPENCG__AUTH__OIDC__INTERNAL_URL: idp.url,
        OPENCG__TENANT: "acme",
      }),
    );
  });
  afterAll(() => idp.close());

  it("accepts a valid token, maps claims, forwards the header, and uses the internal URL", async () => {
    const token = await idp.sign({ preferred_username: "alice", roles: ["admin", "reader"] });
    const r = await auth.authenticate(`Bearer ${token}`);
    expect(r).toEqual({
      ok: true,
      caller: {
        principal: "alice",
        roles: ["admin", "reader"],
        tenant: "acme",
        authMethod: "oidc",
        authorization: `Bearer ${token}`,
      },
    });
    expect(idp.hits).toContain("/realms/opencg/.well-known/openid-configuration");
    expect(idp.hits).toContain("/realms/opencg/protocol/openid-connect/certs");
  });

  it("rejects a missing token as token_missing and counts it", async () => {
    const before = await failures("token_missing");
    expect(await auth.authenticate(undefined)).toMatchObject({ ok: false, reason: "token_missing" });
    expect(await failures("token_missing")).toBe(before + 1);
  });

  it("rejects an expired token beyond the 60 s skew as token_expired", async () => {
    const token = await idp.sign({ preferred_username: "alice" }, { expiresIn: -120 });
    expect(await auth.authenticate(`Bearer ${token}`)).toMatchObject({ ok: false, reason: "token_expired" });
  });

  it("accepts a token expired within the 60 s skew", async () => {
    const token = await idp.sign({ preferred_username: "alice" }, { expiresIn: -30 });
    expect((await auth.authenticate(`Bearer ${token}`)).ok).toBe(true);
  });

  it("rejects a wrong audience and a wrong issuer as token_invalid", async () => {
    const aud = await idp.sign({ preferred_username: "a" }, { audience: "other" });
    expect(await auth.authenticate(`Bearer ${aud}`)).toMatchObject({ ok: false, reason: "token_invalid" });
    const iss = await idp.sign({ preferred_username: "a" }, { issuer: idp.url });
    expect(await auth.authenticate(`Bearer ${iss}`)).toMatchObject({ ok: false, reason: "token_invalid" });
  });

  it("rejects a token without exp as token_invalid", async () => {
    const noExp = await idp.sign({ preferred_username: "a" }, { noExp: true });
    expect(await auth.authenticate(`Bearer ${noExp}`)).toMatchObject({ ok: false, reason: "token_invalid" });
  });

  it("rejects HS256 and alg=none tokens as token_invalid", async () => {
    const hs = await new SignJWT({ preferred_username: "a" })
      .setProtectedHeader({ alg: "HS256" })
      .setIssuer("http://idp.public.invalid/realms/opencg")
      .setAudience("opencg")
      .setExpirationTime("5m")
      .sign(new TextEncoder().encode("a-shared-secret-of-sufficient-length"));
    expect(await auth.authenticate(`Bearer ${hs}`)).toMatchObject({ ok: false, reason: "token_invalid" });
    const none = new UnsecuredJWT({ preferred_username: "a" })
      .setIssuer("http://idp.public.invalid/realms/opencg")
      .setAudience("opencg")
      .setExpirationTime("5m")
      .encode();
    expect(await auth.authenticate(`Bearer ${none}`)).toMatchObject({ ok: false, reason: "token_invalid" });
  });

  it("rejects garbage and an unknown kid as token_invalid", async () => {
    expect(await auth.authenticate("Bearer not.a.jwt")).toMatchObject({ ok: false, reason: "token_invalid" });
    expect(await auth.authenticate("Basic abc")).toMatchObject({ ok: false, reason: "token_missing" });
    const token = await idp.sign({ preferred_username: "a" }, { kid: "unknown" });
    expect(await auth.authenticate(`Bearer ${token}`)).toMatchObject({ ok: false, reason: "token_invalid" });
  });

  it("refuses an ock_ key outside dev as api_key_disabled", async () => {
    expect(await auth.authenticate(`Bearer ${RAW_KEY}`)).toMatchObject({
      ok: false,
      reason: "api_key_disabled",
    });
  });

  it("reports issuer_unreachable when discovery fails", async () => {
    const dead = new Authenticator(
      loadConfig({
        OPENCG__AUTH__MODE: "oidc",
        OPENCG__AUTH__OIDC__ISSUER: "http://127.0.0.1:1/realms/x",
      }),
    );
    const token = await idp.sign({ preferred_username: "a" });
    expect(await dead.authenticate(`Bearer ${token}`)).toMatchObject({
      ok: false,
      reason: "issuer_unreachable",
    });
  });
});

describe("Authenticator API keys", () => {
  const file = keysFile(KEYS);

  it("accepts a configured ock_ key in dev, in oidc mode too", async () => {
    const auth = new Authenticator(
      loadConfig({
        OPENCG__ENVIRONMENT: "dev",
        OPENCG__AUTH__API_KEYS_FILE: file,
        OPENCG__AUTH__MODE: "oidc",
        OPENCG__AUTH__OIDC__ISSUER: "http://127.0.0.1:1/x",
      }),
    );
    expect(await auth.authenticate(`Bearer ${RAW_KEY}`)).toEqual({
      ok: true,
      caller: {
        principal: "ci-bot",
        roles: ["reader"],
        tenant: "default",
        authMethod: "api_key",
        keyName: "ci-bot",
        authorization: `Bearer ${RAW_KEY}`,
      },
    });
    expect(await auth.authenticate("Bearer ock_wrong")).toMatchObject({ ok: false, reason: "token_invalid" });
  });

  it("gates /mcp in none mode once a key is configured", async () => {
    const auth = new Authenticator(loadConfig({ OPENCG__ENVIRONMENT: "dev", OPENCG__AUTH__API_KEYS_FILE: file }));
    expect(auth.open).toBe(false);
    expect(await auth.authenticate(undefined)).toMatchObject({ ok: false, reason: "token_missing" });
  });

  it("accepts the legacy HTTP token in dev as mcp-http-token with the stub identity", async () => {
    const auth = new Authenticator(
      loadConfig({
        OPENCG__ENVIRONMENT: "dev",
        OPENCG__MCP__HTTP_TOKEN: "s3cret",
        OPENCG__IDENTITY__PRINCIPAL: "stub",
        OPENCG__IDENTITY__ROLES: "admin",
      }),
    );
    expect(await auth.authenticate("Bearer s3cret")).toEqual({
      ok: true,
      caller: {
        principal: "stub",
        roles: ["admin"],
        tenant: "default",
        authMethod: "api_key",
        keyName: "mcp-http-token",
        authorization: "Bearer s3cret",
      },
    });
    expect(await auth.authenticate("Bearer nope")).toMatchObject({ ok: false, reason: "token_invalid" });
  });

  it("is open with the stub identity in none mode without keys", async () => {
    const auth = new Authenticator(loadConfig({}));
    expect(auth.open).toBe(true);
    expect(await auth.authenticate(undefined)).toMatchObject({
      ok: true,
      caller: { authMethod: "none", authorization: null, principal: "local-dev" },
    });
    // An ock_ key is still refused outside dev, even when open.
    expect(await auth.authenticate(`Bearer ${RAW_KEY}`)).toMatchObject({ reason: "api_key_disabled" });
  });
});
