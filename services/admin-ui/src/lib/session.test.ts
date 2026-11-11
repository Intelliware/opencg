// @vitest-environment node
import { describe, expect, it } from "vitest";

import { SESSION_TTL_MS, issueSession, passwordMatches, safeNext, verifySession } from "./session";

describe("session tokens", () => {
  it("verifies a freshly issued token", async () => {
    const token = await issueSession("pw", 1_000);
    expect(await verifySession(token, "pw", 2_000)).toBe(true);
  });

  it("rejects a token signed with a different password", async () => {
    const token = await issueSession("old", 1_000);
    expect(await verifySession(token, "new", 2_000)).toBe(false);
  });

  it("rejects an expired token", async () => {
    const token = await issueSession("pw", 1_000);
    expect(await verifySession(token, "pw", 1_000 + SESSION_TTL_MS + 1)).toBe(false);
  });

  it("rejects a token issued in the future", async () => {
    const token = await issueSession("pw", 5_000);
    expect(await verifySession(token, "pw", 1_000)).toBe(false);
  });

  it("rejects a token whose timestamp was altered", async () => {
    const token = await issueSession("pw", 1_000);
    const forged = `2000.${token.split(".")[1]}`;
    expect(await verifySession(forged, "pw", 3_000)).toBe(false);
  });

  it.each([undefined, "", "garbage", ".abc", "abc.def"])("rejects malformed token %p", async (t) => {
    expect(await verifySession(t, "pw", 1_000)).toBe(false);
  });
});

describe("passwordMatches", () => {
  it("matches only the exact password", async () => {
    expect(await passwordMatches("s3cret", "s3cret")).toBe(true);
    expect(await passwordMatches("s3cre", "s3cret")).toBe(false);
    expect(await passwordMatches("", "s3cret")).toBe(false);
  });
});

describe("safeNext", () => {
  it.each([
    ["/graph?tab=map", "/graph?tab=map"],
    [undefined, "/"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
  ])("%p -> %p", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});
