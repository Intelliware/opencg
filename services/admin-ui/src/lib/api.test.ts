// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE, createSession } from "@/lib/auth/session";
import { MemoryStore, setSessionStoreForTests } from "@/lib/auth/store";

const cookieJar = new Map<string, string>();
const requestHeaders = new Headers();

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => (cookieJar.has(name) ? { name, value: cookieJar.get(name)! } : undefined) }),
  headers: async () => requestHeaders,
}));
vi.mock("next/navigation", () => ({
  forbidden: () => {
    throw new Error("NEXT_FORBIDDEN");
  },
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  },
}));
vi.mock("@/lib/auth/oidc", () => ({ refreshTokens: vi.fn() }));

const { listEntities, tombstoneEntity, runGit } = await import("./api");
const { DELETE } = await import("@/app/api/proxy/entities/[id]/route");
const graphRoute = await import("@/app/api/proxy/graph/[...path]/route");

const fetchMock = vi.fn<typeof fetch>();

function sentAuthorization(call = 0): string | undefined {
  const init = fetchMock.mock.calls[call][1] as RequestInit;
  return (init.headers as Record<string, string>).authorization;
}

beforeEach(() => {
  setSessionStoreForTests(new MemoryStore());
  cookieJar.clear();
  requestHeaders.delete("x-opencg-path");
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  setSessionStoreForTests(undefined);
});

async function signIn(createdAgoMs = 60_000): Promise<void> {
  const session = await createSession(
    { accessToken: "alice-token", refreshToken: "rt", expiresIn: 300 },
    Date.now() - createdAgoMs,
  );
  cookieJar.set(SESSION_COOKIE, session.id);
}

describe("pipeline calls in none mode", () => {
  it("send no Authorization header", async () => {
    fetchMock.mockResolvedValue(Response.json({ items: [], total: 0, limit: 50, offset: 0 }));
    await listEntities();
    expect(sentAuthorization()).toBeUndefined();
  });

  it("render the permission-denied page on a pipeline 403", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 403 }));
    await expect(listEntities()).rejects.toThrow("NEXT_FORBIDDEN");
  });
});

describe("pipeline calls in oidc mode", () => {
  beforeEach(() => vi.stubEnv("OPENCG__AUTH__MODE", "oidc"));

  it("attach the session's access token to server-component reads", async () => {
    await signIn();
    fetchMock.mockResolvedValue(Response.json({ items: [], total: 0, limit: 50, offset: 0 }));
    await listEntities({ limit: 5 });
    expect(fetchMock.mock.calls[0][0]).toBe("http://pipeline:8000/entities?limit=5");
    expect(sentAuthorization()).toBe("Bearer alice-token");
  });

  it("attach the token to proxy route handlers and keep content headers", async () => {
    await signIn();
    fetchMock.mockResolvedValue(Response.json({ ok: true }));
    const { NextRequest } = await import("next/server");
    const req = new NextRequest("http://localhost:3000/api/proxy/graph/edges/e1/promote", {
      method: "POST",
      body: JSON.stringify({ reason: "r" }),
    });
    const res = await graphRoute.POST(req, { params: Promise.resolve({ path: ["edges", "e1", "promote"] }) });
    expect(res.status).toBe(200);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.headers).toEqual({ "content-type": "application/json", authorization: "Bearer alice-token" });
  });

  it("send the user to sign in again on a pipeline 401 from a page read", async () => {
    await signIn();
    requestHeaders.set("x-opencg-path", "/entities?source=git");
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    await expect(listEntities()).rejects.toThrow("NEXT_REDIRECT /api/auth/signin?next=%2Fentities%3Fsource%3Dgit");
  });

  it("fail loudly instead of looping when a fresh token is rejected", async () => {
    await signIn(1_000);
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    await expect(listEntities()).rejects.toThrow(/OPENCG__AUTH__OIDC__AUDIENCE/);
  });

  it("turn a 403 on tombstone into a permission-denied JSON response naming the action", async () => {
    await signIn();
    fetchMock.mockResolvedValue(new Response("{}", { status: 403 }));
    await expect(tombstoneEntity("e1")).rejects.toMatchObject({ status: 403 });
    const res = await DELETE(new Request("http://x"), { params: Promise.resolve({ id: "e1" }) });
    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({
      error: "permission_denied",
      action: "tombstone this entity",
      message: "You don't have permission to tombstone this entity.",
    });
  });

  it("names graph actions in a 403 from the graph proxy", async () => {
    await signIn();
    fetchMock.mockResolvedValue(new Response("{}", { status: 403 }));
    const { NextRequest } = await import("next/server");
    const req = new NextRequest("http://localhost:3000/api/proxy/graph/edges/e1/promote", { method: "POST", body: "{}" });
    const res = await graphRoute.POST(req, { params: Promise.resolve({ path: ["edges", "e1", "promote"] }) });
    expect(res.status).toBe(403);
    expect((await res.json()).message).toBe("You don't have permission to promote this relationship.");
  });

  it("propagate an auth failure from runGit instead of reporting the pipeline unreachable", async () => {
    await signIn();
    fetchMock.mockResolvedValue(new Response("{}", { status: 403 }));
    await expect(runGit("https://github.com/a/b")).rejects.toMatchObject({ status: 403 });
  });
});
