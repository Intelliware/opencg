// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { refreshTokens } from "./oidc";
import {
  REFRESH_MARGIN_MS,
  SESSION_TTL_SECONDS,
  createSession,
  loadSession,
  peekSession,
  safeNext,
  savePendingSignin,
  signinPath,
  takePendingSignin,
} from "./session";
import { MemoryStore, setSessionStoreForTests } from "./store";

vi.mock("./oidc", () => ({ refreshTokens: vi.fn() }));

const refresh = vi.mocked(refreshTokens);

function jwt(payload: Record<string, unknown>): string {
  const part = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${part({ alg: "RS256" })}.${part(payload)}.sig`;
}

let now = 1_000_000_000_000;
let store: MemoryStore;

beforeEach(() => {
  now = 1_000_000_000_000;
  store = new MemoryStore(() => now);
  setSessionStoreForTests(store);
  refresh.mockReset();
});
afterEach(() => {
  setSessionStoreForTests(undefined);
  vi.unstubAllEnvs();
});

describe("createSession", () => {
  it("stores tokens server-side under a random id with the display identity", async () => {
    const session = await createSession(
      { accessToken: jwt({ preferred_username: "alice", roles: ["admin"], sub: "u1" }), refreshToken: "rt", idToken: "it", expiresIn: 300 },
      now,
    );
    expect(session.id).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(session.principal).toBe("alice");
    expect(session.roles).toEqual(["admin"]);
    expect(session.accessTokenExpiresAt).toBe(now + 300_000);
    const stored = JSON.parse((await store.get(`opencg:admin-ui:session:${session.id}`))!);
    expect(stored.refreshToken).toBe("rt");
    expect(store.data.get(`opencg:admin-ui:session:${session.id}`)!.expiresAt).toBe(now + SESSION_TTL_SECONDS * 1000);
  });

  it("uses the configured claims and falls back to sub", async () => {
    vi.stubEnv("OPENCG__AUTH__OIDC__PRINCIPAL_CLAIM", "email");
    vi.stubEnv("OPENCG__AUTH__OIDC__ROLES_CLAIM", "realm_access.roles");
    const session = await createSession(
      { accessToken: jwt({ sub: "u2", realm_access: { roles: ["reader"] } }), expiresIn: 60 },
      now,
    );
    expect(session.principal).toBe("u2");
    expect(session.roles).toEqual(["reader"]);
  });
});

describe("loadSession", () => {
  it("returns a session whose token is not near expiry without refreshing", async () => {
    const { id } = await createSession({ accessToken: "at", refreshToken: "rt", expiresIn: 300 }, now);
    now += 300_000 - REFRESH_MARGIN_MS - 1;
    expect((await loadSession(id, now))?.accessToken).toBe("at");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refreshes within 60 s of expiry and stores the new tokens", async () => {
    const { id } = await createSession({ accessToken: "at", refreshToken: "rt", idToken: "it", expiresIn: 300 }, now);
    now += 300_000 - REFRESH_MARGIN_MS;
    refresh.mockResolvedValue({ accessToken: "at2", refreshToken: "rt2", expiresIn: 300 });
    const session = await loadSession(id, now);
    expect(refresh).toHaveBeenCalledWith("rt");
    expect(session?.accessToken).toBe("at2");
    expect(session?.accessTokenExpiresAt).toBe(now + 300_000);
    expect(session?.idToken).toBe("it");
    expect((await peekSession(id))?.refreshToken).toBe("rt2");
  });

  it("shares one refresh between concurrent requests", async () => {
    const { id } = await createSession({ accessToken: "at", refreshToken: "rt", expiresIn: 30 }, now);
    refresh.mockResolvedValue({ accessToken: "at2", expiresIn: 300 });
    const [a, b] = await Promise.all([loadSession(id, now), loadSession(id, now)]);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(a?.accessToken).toBe("at2");
    expect(b?.accessToken).toBe("at2");
  });

  it("ends the session when the refresh fails", async () => {
    const { id } = await createSession({ accessToken: "at", refreshToken: "rt", expiresIn: 300 }, now);
    now += 301_000;
    refresh.mockRejectedValue(new Error("invalid_grant"));
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(await loadSession(id, now)).toBeNull();
    expect(await peekSession(id)).toBeNull();
  });

  it("ends an expired session that has no refresh token", async () => {
    const { id } = await createSession({ accessToken: "at", expiresIn: 30 }, now);
    expect(await loadSession(id, now)).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("ignores missing and malformed ids", async () => {
    expect(await loadSession(undefined, now)).toBeNull();
    expect(await loadSession("../../etc", now)).toBeNull();
  });

  it("expires with the store TTL", async () => {
    const { id } = await createSession({ accessToken: "at", refreshToken: "rt", expiresIn: 300 }, now);
    now += SESSION_TTL_SECONDS * 1000;
    expect(await loadSession(id, now)).toBeNull();
  });
});

describe("pending sign-in", () => {
  it("is usable once", async () => {
    await savePendingSignin("s1", { codeVerifier: "v", nonce: "n", next: "/graph" });
    expect(await takePendingSignin("s1")).toEqual({ codeVerifier: "v", nonce: "n", next: "/graph" });
    expect(await takePendingSignin("s1")).toBeNull();
  });
});

describe("safeNext", () => {
  it.each([
    ["/graph?tab=map", "/graph?tab=map"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["https://evil.example/", "/"],
    ["javascript:alert(1)", "/"],
    ["/ok\n", "/"],
    [null, "/"],
    ["", "/"],
  ])("maps %j to %j", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });

  it("builds the sign-in path with an encoded, sanitised next", () => {
    expect(signinPath("/graph?tab=map")).toBe("/api/auth/signin?next=%2Fgraph%3Ftab%3Dmap");
    expect(signinPath("//evil.example")).toBe("/api/auth/signin?next=%2F");
  });
});
