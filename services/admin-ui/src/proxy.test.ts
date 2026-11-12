// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE, issueSession } from "@/lib/session";
import { proxy } from "./proxy";

const req = (path: string, cookie?: string) =>
  new NextRequest(new URL(path, "http://localhost:3000"), {
    headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {},
  });

afterEach(() => vi.unstubAllEnvs());

describe("admin access gate proxy", () => {
  it("passes everything through when no password is configured", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "");
    const res = await proxy(req("/api/proxy/entities/abc"));
    expect(res.headers.get("x-middleware-next")).toBe("1");
  });

  it("blocks an unauthenticated proxy call with 401", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await proxy(req("/api/proxy/entities/abc"));
    expect(res.status).toBe(401);
    expect(res.headers.get("x-middleware-next")).toBeNull();
  });

  it("redirects an unauthenticated page view to /login with next", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await proxy(req("/graph?tab=map"));
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/graph?tab=map");
  });

  it("lets a valid session through", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await proxy(req("/api/proxy/entities/abc", await issueSession("pw")));
    expect(res.headers.get("x-middleware-next")).toBe("1");
  });

  it("rejects a session issued under a different password", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await proxy(req("/api/proxy/entities/abc", await issueSession("other")));
    expect(res.status).toBe(401);
  });

  it.each(["/login", "/api/auth/login", "/api/healthz"])("leaves %s public", async (path) => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await proxy(req(path));
    expect(res.headers.get("x-middleware-next")).toBe("1");
  });
});
