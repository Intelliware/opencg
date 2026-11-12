import { describe, expect, it } from "vitest";

import { authMode, oidcSettings, startupProblems } from "./config";

const OIDC = {
  OPENCG__AUTH__MODE: "oidc",
  OPENCG__AUTH__OIDC__ISSUER: "http://localhost:8380/realms/opencg",
  OPENCG__ADMIN_UI__OIDC__CLIENT_SECRET: "s",
  OPENCG__ADMIN_UI__PUBLIC_URL: "http://localhost:3300",
};

describe("authMode", () => {
  it("defaults to none", () => {
    expect(authMode({})).toBe("none");
    expect(authMode({ OPENCG__AUTH__MODE: " " })).toBe("none");
  });

  it("rejects an unknown mode", () => {
    expect(() => authMode({ OPENCG__AUTH__MODE: "basic" })).toThrow(/OPENCG__AUTH__MODE/);
  });
});

describe("oidcSettings", () => {
  it("applies the documented defaults and defaults the internal URL to the issuer", () => {
    const s = oidcSettings({ OPENCG__AUTH__OIDC__ISSUER: "http://idp/realms/x/" });
    expect(s).toMatchObject({
      issuer: "http://idp/realms/x",
      internalUrl: "http://idp/realms/x",
      audience: "opencg",
      principalClaim: "preferred_username",
      rolesClaim: "roles",
      clientId: "opencg-admin-ui",
    });
  });
});

describe("startupProblems", () => {
  it("accepts default none mode and a complete oidc config", () => {
    expect(startupProblems({})).toEqual([]);
    expect(startupProblems(OIDC)).toEqual([]);
  });

  it.each(["OPENCG__ADMIN_UI__PASSWORD", "OPENCG__MCP__OAUTH_PASSWORD"])(
    "refuses the removed stopgap %s and points to the migration docs",
    (key) => {
      const [problem] = startupProblems({ [key]: "pw" });
      expect(problem).toContain(key);
      expect(problem).toContain("docs/OPERATIONS.md");
    },
  );

  it("refuses an unknown mode", () => {
    expect(startupProblems({ OPENCG__AUTH__MODE: "open" })[0]).toContain("OPENCG__AUTH__MODE");
  });

  it("refuses none mode on a non-loopback bind address", () => {
    const [problem] = startupProblems({ OPENCG__BIND_ADDRESS: "0.0.0.0" });
    expect(problem).toContain("OPENCG__AUTH__MODE");
    expect(problem).toContain("OPENCG__BIND_ADDRESS");
    expect(startupProblems({ OPENCG__BIND_ADDRESS: "127.0.0.1" })).toEqual([]);
  });

  it("refuses oidc mode without an issuer, an explicitly empty audience or the client settings", () => {
    const problems = startupProblems({ OPENCG__AUTH__MODE: "oidc", OPENCG__AUTH__OIDC__AUDIENCE: "" });
    expect(problems.join("\n")).toContain("OPENCG__AUTH__OIDC__ISSUER");
    expect(problems.join("\n")).toContain("OPENCG__AUTH__OIDC__AUDIENCE");
    expect(problems.join("\n")).toContain("OPENCG__ADMIN_UI__OIDC__CLIENT_SECRET");
    expect(problems.join("\n")).toContain("OPENCG__ADMIN_UI__PUBLIC_URL");
  });
});
