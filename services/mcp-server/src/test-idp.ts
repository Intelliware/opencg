// Test-only helpers: a local OIDC issuer (discovery + JWKS over HTTP) with a
// freshly generated signing key, and a token minter. Not imported by runtime code.

import { createServer, type Server as HttpServer } from "node:http";
import type { AddressInfo } from "node:net";
import { exportJWK, generateKeyPair, type JWTPayload, SignJWT } from "jose";

export interface TestIdp {
  /** Base URL of the local server (use as INTERNAL_URL, or as the issuer). */
  url: string;
  /** Requests served, by path. */
  hits: string[];
  sign(claims: JWTPayload, opts?: SignOpts): Promise<string>;
  close(): Promise<void>;
}

export interface SignOpts {
  issuer?: string;
  audience?: string | string[];
  /** Seconds relative to now. */
  expiresIn?: number;
  kid?: string;
  /** Omit the `exp` claim. */
  noExp?: boolean;
}

/**
 * `issuerPath` is appended to the server URL; `publicIssuer`, when given, is
 * what discovery advertises (and what `jwks_uri` uses as its origin), like a
 * Keycloak whose public hostname differs from the compose-internal one.
 */
export async function startTestIdp(opts: { issuerPath?: string; publicIssuer?: string } = {}): Promise<TestIdp> {
  const { privateKey, publicKey } = await generateKeyPair("RS256");
  const jwk = { ...(await exportJWK(publicKey)), kid: "k1", alg: "RS256", use: "sig" };
  const issuerPath = opts.issuerPath ?? "/realms/opencg";
  const hits: string[] = [];
  let base = "";

  const server: HttpServer = createServer((req, res) => {
    const path = (req.url ?? "").split("?")[0] ?? "";
    hits.push(path);
    const issuer = opts.publicIssuer ?? `${base}${issuerPath}`;
    if (path === `${issuerPath}/.well-known/openid-configuration`) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ issuer, jwks_uri: `${issuer}/protocol/openid-connect/certs` }));
      return;
    }
    if (path === `${issuerPath}/protocol/openid-connect/certs`) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ keys: [jwk] }));
      return;
    }
    res.writeHead(404);
    res.end();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const url = `${base}${issuerPath}`;

  return {
    url,
    hits,
    async sign(claims, o = {}) {
      const now = Math.floor(Date.now() / 1000);
      const jwt = new SignJWT(claims)
        .setProtectedHeader({ alg: "RS256", kid: o.kid ?? "k1" })
        .setIssuer(o.issuer ?? opts.publicIssuer ?? url)
        .setAudience(o.audience ?? "opencg")
        .setIssuedAt(now);
      if (!o.noExp) jwt.setExpirationTime(now + (o.expiresIn ?? 300));
      return jwt.sign(privateKey);
    },
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

/** A recording stand-in for the pipeline: status per path, last headers kept. */
export interface FakePipelineServer {
  url: string;
  requests: { path: string; authorization: string | undefined; correlationId: string | undefined }[];
  respond: { status: number; body: unknown };
  close(): Promise<void>;
}

export async function startFakePipeline(): Promise<FakePipelineServer> {
  const state: FakePipelineServer = {
    url: "",
    requests: [],
    respond: { status: 200, body: null },
    close: async () => undefined,
  };
  const server = createServer((req, res) => {
    const path = (req.url ?? "").split("?")[0] ?? "";
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      state.requests.push({
        path,
        authorization: req.headers.authorization,
        correlationId: req.headers["x-correlation-id"] as string | undefined,
      });
      let body = state.respond.body;
      if (body === null && path === "/retrieve") {
        const sent = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}") as {
          correlation_id?: string;
        };
        body = {
          correlation_id: sent.correlation_id,
          fragments: [],
          usage: { total_tokens_in: 0, total_tokens_out: 0, total_latency_ms: 1, by_stage: [] },
          final_context_hash: "x",
        };
      }
      if (body === null) body = { nodes: [], edges: [] };
      res.writeHead(state.respond.status, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  state.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  state.close = () => new Promise<void>((resolve) => server.close(() => resolve()));
  return state;
}
