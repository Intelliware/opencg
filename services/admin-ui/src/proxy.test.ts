// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE, createSession } from "@/lib/auth/session";
import { MemoryStore, setSessionStoreForTests } from "@/lib/auth/store";
import { proxy } from "./proxy";

vi.mock("@/lib/auth/oidc", () => ({
  refreshTokens: vi.fn(async () => {
    throw new Error("revoked");
  }),
}));

const req = (path: string, cookie?: string) =>
  new NextRequest(new URL(path, "http://localhost:3000"), {
    headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {},
  });

const passedThrough = (res: Response) => res.headers.get("x-middleware-next") === "1";

beforeEach(() => setSessionStoreForTests(new MemoryStore()));
afterEach(() => {
  vi.unstubAllEnvs();
  setSessionStoreForTests(undefined);
});

describe("admin UI proxy in none mode", () => {
  it("passes every request through", async () => {
    vi.stubEnv("OPENCG__AUTH__MODE", "");
    expect(passedThrough(await proxy(req("/api/proxy/entities/abc")))).toBe(true);
    expect(passedThrough(await proxy(req("/graph")))).toBe(true);
  });
});

describe("admin UI proxy in oidc mode", () => {
  beforeEach(() => {
    vi.stubEnv("OPENCG__AUTH__MODE", "oidc");
    vi.stubEnv("OPENCG__ADMIN_UI__PUBLIC_URL", "http://localhost:3300");
  });

  it("answers an unauthenticated /api/** call with 401 JSON", async () => {
    const res = await proxy(req("/api/proxy/entities/abc"));
    expect(res.status).toBe(401);
    expect(passedThrough(res)).toBe(false);
    expect(await res.json()).toMatchObject({ error: "signin_required" });
  });

  it("redirects an unauthenticated page view to sign-in with next", async () => {
    const res = await proxy(req("/graph?tab=map"));
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.origin).toBe("http://localhost:3300");
    expect(location.pathname).toBe("/api/auth/signin");
    expect(location.searchParams.get("next")).toBe("/graph?tab=map");
  });

  it("lets a valid session through and records the path for re-sign-in", async () => {
    const session = await createSession({ accessToken: "at", refreshToken: "rt", expiresIn: 300 });
    const res = await proxy(req("/ingestion", session.id));
    expect(passedThrough(res)).toBe(true);
    expect(res.headers.get("x-middleware-request-x-opencg-path")).toBe("/ingestion");
  });

  it("rejects an unknown session id", async () => {
    const res = await proxy(req("/api/proxy/search/vector", "x".repeat(43)));
    expect(res.status).toBe(401);
  });

  it("treats a session whose refresh failed as signed out", async () => {
    const session = await createSession({ accessToken: "at", refreshToken: "rt", expiresIn: 10 });
    const res = await proxy(req("/ingestion", session.id));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/api/auth/signin");
  });

  it.each(["/api/auth/signin", "/api/auth/callback", "/api/auth/signout", "/api/healthz"])(
    "leaves %s open",
    async (path) => {
      expect(passedThrough(await proxy(req(path)))).toBe(true);
    },
  );

  it("returns 503 when the session store is down", async () => {
    setSessionStoreForTests({
      get: async () => {
        throw new Error("ECONNREFUSED");
      },
      set: async () => undefined,
      del: async () => undefined,
    });
    const res = await proxy(req("/api/proxy/entities/abc", "y".repeat(43)));
    expect(res.status).toBe(503);
  });
});
