import { describe, expect, it } from "vitest";

import { claimAt, identityFromClaims } from "./claims";

describe("claims", () => {
  it("reads dotted paths", () => {
    expect(claimAt({ realm_access: { roles: ["a"] } }, "realm_access.roles")).toEqual(["a"]);
    expect(claimAt({}, "a.b")).toBeUndefined();
  });

  it("prefers the access token, then the ID token, then sub", () => {
    expect(identityFromClaims([{ sub: "s" }, { preferred_username: "alice", roles: "admin reader" }], "preferred_username", "roles")).toEqual({
      principal: "alice",
      roles: ["admin", "reader"],
    });
    expect(identityFromClaims([{ sub: "s" }], "preferred_username", "roles")).toEqual({ principal: "s", roles: [] });
  });
});
