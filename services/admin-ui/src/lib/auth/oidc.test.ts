import { describe, expect, it, vi } from "vitest";

import { oidcSettings } from "./config";
import { internalFetch, toInternalUrl } from "./oidc";

const ISSUER = "http://localhost:8380/realms/opencg";
const INTERNAL = "http://keycloak:8080/realms/opencg";

describe("toInternalUrl", () => {
  it("rewrites discovery, token and JWKS URLs under the public issuer", () => {
    expect(toInternalUrl(`${ISSUER}/.well-known/openid-configuration`, ISSUER, INTERNAL)).toBe(
      `${INTERNAL}/.well-known/openid-configuration`,
    );
    expect(toInternalUrl(`${ISSUER}/protocol/openid-connect/token`, ISSUER, INTERNAL)).toBe(
      `${INTERNAL}/protocol/openid-connect/token`,
    );
  });

  it("rewrites other paths on the public origin by origin", () => {
    expect(toInternalUrl("http://localhost:8380/resources/jwks", ISSUER, INTERNAL)).toBe(
      "http://keycloak:8080/resources/jwks",
    );
  });

  it("leaves foreign URLs and identical public/internal URLs alone", () => {
    expect(toInternalUrl("https://other.example/x", ISSUER, INTERNAL)).toBe("https://other.example/x");
    expect(toInternalUrl(`${ISSUER}/x`, ISSUER, ISSUER)).toBe(`${ISSUER}/x`);
  });

  it("is applied by the custom fetch used for every server-side IdP call", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}"));
    const settings = oidcSettings({ OPENCG__AUTH__OIDC__ISSUER: ISSUER, OPENCG__AUTH__OIDC__INTERNAL_URL: INTERNAL });
    await internalFetch(settings, fetchImpl as unknown as typeof fetch)(`${ISSUER}/protocol/openid-connect/certs`, {
      method: "GET",
    } as never);
    expect(fetchImpl).toHaveBeenCalledWith(`${INTERNAL}/protocol/openid-connect/certs`, { method: "GET" });
  });
});
