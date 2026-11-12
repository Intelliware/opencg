// The bundled Keycloak's login page and token endpoint (oidc mode).
import type { Page } from "@playwright/test";

import { OIDC_ISSUER, SERVICE_CLIENT } from "./env";

/** On the Keycloak login page: fill the form and submit. */
export async function signInThroughIdp(page: Page, username: string, password: string): Promise<void> {
  await page.waitForURL((url) => url.href.startsWith(`${OIDC_ISSUER}/`));
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
}

/**
 * A client-credentials access token for the service account, refreshed before
 * it expires (the dev realm issues 300 s tokens). One per worker.
 */
export class ServiceToken {
  private token = "";
  private expiresAt = 0;

  async get(): Promise<string> {
    if (this.token && Date.now() < this.expiresAt - 60_000) return this.token;
    const secret = SERVICE_CLIENT.secret();
    if (!secret) throw new Error("OPENCG__SMOKE__CLIENT_SECRET is not set (environment or .env)");
    const res = await fetch(`${OIDC_ISSUER}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "client_credentials",
        client_id: SERVICE_CLIENT.id,
        client_secret: secret,
      }),
    });
    if (!res.ok) throw new Error(`token request for ${SERVICE_CLIENT.id} failed: HTTP ${res.status}`);
    const body = (await res.json()) as { access_token: string; expires_in: number };
    this.token = body.access_token;
    this.expiresAt = Date.now() + body.expires_in * 1000;
    return this.token;
  }
}
