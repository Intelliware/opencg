// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE, verifySession } from "@/lib/session";
import { POST as logout } from "../logout/route";
import { POST } from "./route";

const submit = (fields: Record<string, string>, headers?: HeadersInit) =>
  POST(
    new Request("http://0.0.0.0:3000/api/auth/login", {
      method: "POST",
      body: new URLSearchParams(fields),
      headers,
    }),
  );

// Relative, so the browser resolves it against the host it used, never 0.0.0.0.
const location = (res: Response) => new URL(res.headers.get("location")!, "http://browser.test");

afterEach(() => vi.unstubAllEnvs());

describe("POST /api/auth/login", () => {
  it("sets a valid session cookie and redirects to next on the right password", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await submit({ password: "pw", next: "/ingestion" });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/ingestion");
    const cookie = res.headers.get("set-cookie")!;
    expect(cookie).toContain(`${SESSION_COOKIE}=`);
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie.toLowerCase()).not.toContain("secure");
    const token = decodeURIComponent(cookie.split(";")[0].split("=")[1]);
    expect(await verifySession(token, "pw")).toBe(true);
  });

  it("marks the cookie Secure behind a TLS-terminating proxy", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await submit({ password: "pw" }, { "x-forwarded-proto": "https" });
    expect(res.headers.get("set-cookie")!.toLowerCase()).toContain("secure");
  });

  it("redirects back to /login with an error and no cookie on a wrong password", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await submit({ password: "nope", next: "/ingestion" });
    const loc = location(res);
    expect(loc.pathname).toBe("/login");
    expect(loc.searchParams.get("error")).toBe("1");
    expect(loc.searchParams.get("next")).toBe("/ingestion");
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("never redirects off-site", async () => {
    vi.stubEnv("OPENCG__ADMIN_UI__PASSWORD", "pw");
    const res = await submit({ password: "pw", next: "//evil.example/x" });
    expect(res.headers.get("location")).toBe("/");
  });
});

describe("POST /api/auth/logout", () => {
  it("clears the session cookie and redirects to /login", async () => {
    const res = await logout();
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/login");
    expect(res.headers.get("set-cookie")).toMatch(new RegExp(`${SESSION_COOKIE}=;`));
  });
});
