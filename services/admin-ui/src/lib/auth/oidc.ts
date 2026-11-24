// openid-client configuration for the admin UI (design D3, D11).
//
// Browsers reach the IdP at the public issuer; the admin UI container reaches
// it at OPENCG__AUTH__OIDC__INTERNAL_URL. Discovery is requested for the public
// issuer (so `iss` checks use it) but every server-side fetch — discovery,
// token, JWKS, userinfo — is rewritten to the internal origin. The
// authorization and end-session endpoints are never fetched server-side, so
// the URLs built from them stay public.
import * as client from "openid-client";

import { oidcSettings, type OidcSettings } from "./config";

/** Rewrite a URL under the public issuer (or its origin) to the internal URL. */
export function toInternalUrl(url: string, issuer: string, internalUrl: string): string {
  if (!internalUrl || issuer === internalUrl) return url;
  if (url === issuer || url.startsWith(`${issuer}/`)) return internalUrl + url.slice(issuer.length);
  const target = new URL(url);
  const publicOrigin = new URL(issuer).origin;
  if (target.origin !== publicOrigin) return url;
  const internal = new URL(internalUrl);
  target.protocol = internal.protocol;
  target.host = internal.host;
  return target.toString();
}

export function internalFetch(settings: OidcSettings, fetchImpl: typeof fetch = fetch): client.CustomFetch {
  return (url, options) =>
    fetchImpl(toInternalUrl(url, settings.issuer, settings.internalUrl), options as RequestInit);
}

let configuration: Promise<client.Configuration> | null = null;

async function discover(settings: OidcSettings): Promise<client.Configuration> {
  const insecure = [settings.issuer, settings.internalUrl].some((url) => url.startsWith("http:"));
  return client.discovery(
    new URL(settings.issuer),
    settings.clientId,
    undefined,
    settings.clientSecret ? client.ClientSecretPost(settings.clientSecret) : client.None(),
    {
      [client.customFetch]: internalFetch(settings),
      // Plain-HTTP issuers only occur with the bundled dev IdP.
      execute: insecure ? [client.allowInsecureRequests] : [],
    },
  );
}

/** Discovered configuration, cached per process; a failed discovery is retried. */
export function oidcConfig(): Promise<client.Configuration> {
  if (!configuration) {
    configuration = discover(oidcSettings()).catch((error: unknown) => {
      configuration = null;
      throw error;
    });
  }
  return configuration;
}

export function resetOidcConfigForTests(): void {
  configuration = null;
}

export interface TokenResult {
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  /** Seconds until the access token expires, when the IdP says. */
  expiresIn?: number;
  idTokenClaims?: Record<string, unknown>;
}

function toResult(tokens: client.TokenEndpointResponse & client.TokenEndpointResponseHelpers): TokenResult {
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
    expiresIn: tokens.expiresIn(),
    idTokenClaims: tokens.claims() as Record<string, unknown> | undefined,
  };
}

export async function refreshTokens(refreshToken: string): Promise<TokenResult> {
  return toResult(await client.refreshTokenGrant(await oidcConfig(), refreshToken));
}

export interface AuthorizationCodeChecks {
  codeVerifier: string;
  state: string;
  nonce: string;
}

export async function exchangeCode(currentUrl: URL, checks: AuthorizationCodeChecks, redirectUri: string): Promise<TokenResult> {
  const tokens = await client.authorizationCodeGrant(
    await oidcConfig(),
    currentUrl,
    {
      pkceCodeVerifier: checks.codeVerifier,
      expectedState: checks.state,
      expectedNonce: checks.nonce,
      idTokenExpected: true,
    },
    { redirect_uri: redirectUri },
  );
  return toResult(tokens);
}

export interface AuthorizationStart {
  url: URL;
  codeVerifier: string;
  state: string;
  nonce: string;
}

export async function startAuthorization(settings: OidcSettings, redirectUri: string): Promise<AuthorizationStart> {
  const codeVerifier = client.randomPKCECodeVerifier();
  const state = client.randomState();
  const nonce = client.randomNonce();
  const url = client.buildAuthorizationUrl(await oidcConfig(), {
    redirect_uri: redirectUri,
    scope: settings.scope,
    code_challenge: await client.calculatePKCECodeChallenge(codeVerifier),
    code_challenge_method: "S256",
    state,
    nonce,
  });
  return { url, codeVerifier, state, nonce };
}

/** RP-initiated logout URL, or null when the IdP has no end-session endpoint. */
export async function endSessionUrl(params: { idTokenHint?: string; postLogoutRedirectUri: string }): Promise<URL | null> {
  const config = await oidcConfig();
  if (!config.serverMetadata().end_session_endpoint) return null;
  const query: Record<string, string> = {
    post_logout_redirect_uri: params.postLogoutRedirectUri,
    client_id: config.clientMetadata().client_id,
  };
  if (params.idTokenHint) query.id_token_hint = params.idTokenHint;
  return client.buildEndSessionUrl(config, query);
}
