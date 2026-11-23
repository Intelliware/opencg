// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { exchangeCode, endSessionUrl, startAuthorization } from "@/lib/auth/oidc";
import { SESSION_COOKIE, SIGNIN_COOKIE, createSession, peekSession } from "@/lib/auth/session";
import { MemoryStore, setSessionStoreForTests } from "@/lib/auth/store";

import { GET as callback } from "./callback/route";
import { GET as signin } from "./signin/route";
import { POST as signout } from "./signout/route";

vi.mock("@/lib/auth/oidc", () => ({
  startAuthorization: vi.fn(),
  exchangeCode: vi.fn(),
  endSessionUrl: vi.fn(),
  refreshTokens: vi.fn(),
}));

const start = vi.mocked(startAuthorization);
const exchange = vi.mocked(exchangeCode);
const endSession = vi.mocked(endSessionUrl);

const PUBLIC = "http://localhost:3300";

beforeEach(() => {
  setSessionStoreForTests(new MemoryStore());
  vi.stubEnv("OPENCG__AUTH__MODE", "oidc");
  vi.stubEnv("OPENCG__AUTH__OIDC__ISSUER", "http://localhost:8380/realms/opencg");
  vi.stubEnv("OPENCG__ADMIN_UI__PUBLIC_URL", PUBLIC);
  start.mockResolvedValue({
    url: new URL("http://localhost:8380/realms/opencg/protocol/openid-connect/auth?client_id=opencg-admin-ui"),
    codeVerifier: "verifier",
    state: "state-1",
    nonce: "nonce-1",
  });
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  setSessionStoreForTests(undefined);
});

async function begin(next: string) {
  const res = await signin(new Request(`http://0.0.0.0:3000/api/auth/signin?next=${encodeURIComponent(next)}`));
  return res;
}

async function finish(cookieState = "state-1", query = "code=abc&state=state-1") {
  return callback(
    new NextRequest(`http://0.0.0.0:3000/api/auth/callback?${query}`, {
      headers: { cookie: `${SIGNIN_COOKIE}=${cookieState}` },
    }),
  );
}

describe("sign-in", () => {
  it("redirects to the IdP with the callback URL and binds state to the browser", async () => {
    const res = await begin("/graph");
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toContain("http://localhost:8380/realms/opencg/protocol/openid-connect/auth");
    expect(start).toHaveBeenCalledWith(expect.objectContaining({ clientId: "opencg-admin-ui" }), `${PUBLIC}/api/auth/callback`);
    const cookie = res.headers.get("set-cookie")!;
    expect(cookie).toContain(`${SIGNIN_COOKIE}=state-1`);
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=lax");
    expect(cookie).not.toContain("Secure");
  });

  it("completes the flow and lands on the requested path with only a session id cookie", async () => {
    exchange.mockResolvedValue({ accessToken: "ACCESS-TOKEN", refreshToken: "REFRESH-TOKEN", idToken: "ID-TOKEN", expiresIn: 300 });
    await begin("/graph?tab=map");
    const res = await finish();
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/graph?tab=map");
    expect(exchange).toHaveBeenCalledWith(
      new URL(`${PUBLIC}/api/auth/callback?code=abc&state=state-1`),
      { codeVerifier: "verifier", state: "state-1", nonce: "nonce-1" },
      `${PUBLIC}/api/auth/callback`,
    );
    const setCookie = res.headers.getSetCookie().find((c) => c.startsWith(`${SESSION_COOKIE}=`))!;
    const id = /opencg_session=([^;]+)/.exec(setCookie)![1];
    expect(setCookie).toContain("HttpOnly");
    const allCookies = res.headers.getSetCookie().join("\n");
    for (const token of ["ACCESS-TOKEN", "REFRESH-TOKEN", "ID-TOKEN"]) expect(allCookies).not.toContain(token);
    expect((await peekSession(id))?.accessToken).toBe("ACCESS-TOKEN");
  });

  it("refuses an open redirect in next and lands on /", async () => {
    exchange.mockResolvedValue({ accessToken: "at", expiresIn: 300 });
    await begin("//evil.example");
    const res = await finish();
    expect(res.headers.get("location")).toBe("/");
  });

  it("rejects a callback whose state does not match the browser's cookie", async () => {
    await begin("/");
    const res = await finish("other-state");
    expect(res.status).toBe(400);
    expect(exchange).not.toHaveBeenCalled();
  });

  it("rejects a replayed state", async () => {
    exchange.mockResolvedValue({ accessToken: "at", expiresIn: 300 });
    await begin("/");
    await finish();
    expect((await finish()).status).toBe(400);
  });

  it("sets Secure cookies when the public URL is https", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PUBLIC_URL", "https://admin.example");
    const res = await begin("/");
    expect(res.headers.get("set-cookie")).toContain("Secure");
  });

  it("passes straight through in none mode", async () => {
    vi.stubEnv("OPENCG__AUTH__MODE", "none");
    const res = await begin("/graph");
    expect(res.headers.get("location")).toBe("/graph");
    expect(start).not.toHaveBeenCalled();
  });
});

describe("sign-out", () => {
  it("deletes the session and redirects to the IdP end-session endpoint", async () => {
    const session = await createSession({ accessToken: "at", idToken: "the-id-token", expiresIn: 300 });
    endSession.mockResolvedValue(new URL("http://localhost:8380/logout?id_token_hint=the-id-token"));
    const res = await signout(
      new NextRequest("http://0.0.0.0:3000/api/auth/signout", {
        method: "POST",
        headers: { cookie: `${SESSION_COOKIE}=${session.id}` },
      }),
    );
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("http://localhost:8380/logout?id_token_hint=the-id-token");
    expect(endSession).toHaveBeenCalledWith({ idTokenHint: "the-id-token", postLogoutRedirectUri: `${PUBLIC}/` });
    expect(await peekSession(session.id)).toBeNull();
    expect(res.headers.get("set-cookie")).toMatch(/opencg_session=;/);
  });
});
