// Server-side admin UI sessions (design D11).
//
// The browser holds only an opaque random id in the `opencg_session` cookie
// (HttpOnly, SameSite=Lax, Secure over HTTPS). Tokens, their expiry and the
// display identity live in Valkey under `opencg:admin-ui:session:<id>`.
// The access token is refreshed when it is within REFRESH_MARGIN_MS of expiry;
// a failed refresh ends the session.
import { randomBytes } from "node:crypto";

import { identityFromClaims, decodeJwtPayload, type Identity } from "./claims";
import { oidcSettings } from "./config";
import { refreshTokens, type TokenResult } from "./oidc";
import { sessionStore } from "./store";

export const SESSION_COOKIE = "opencg_session";
export const SIGNIN_COOKIE = "opencg_signin";
/** Request header the proxy sets to the requested path (sign-in `next` after a pipeline 401). */
export const PATH_HEADER = "x-opencg-path";
/** Absolute session lifetime; the IdP's own session usually ends sooner. */
export const SESSION_TTL_SECONDS = 12 * 60 * 60;
export const SIGNIN_TTL_SECONDS = 10 * 60;
export const REFRESH_MARGIN_MS = 60_000;
/** Assumed access-token lifetime when the IdP omits `expires_in`. */
const DEFAULT_ACCESS_TTL_S = 300;

const SESSION_KEY = (id: string) => `opencg:admin-ui:session:${id}`;
const SIGNIN_KEY = (state: string) => `opencg:admin-ui:signin:${state}`;

export interface Session extends Identity {
  id: string;
  accessToken: string;
  /** Epoch ms. */
  accessTokenExpiresAt: number;
  refreshToken?: string;
  idToken?: string;
  /** Epoch ms. */
  createdAt: number;
}

export function newSessionId(): string {
  return randomBytes(32).toString("base64url");
}

function identityOf(tokens: TokenResult): Identity {
  const settings = oidcSettings();
  return identityFromClaims(
    [decodeJwtPayload(tokens.accessToken), tokens.idTokenClaims],
    settings.principalClaim,
    settings.rolesClaim,
  );
}

function accessExpiry(tokens: TokenResult, now: number): number {
  if (typeof tokens.expiresIn === "number") return now + tokens.expiresIn * 1000;
  const exp = decodeJwtPayload(tokens.accessToken)?.exp;
  return typeof exp === "number" ? exp * 1000 : now + DEFAULT_ACCESS_TTL_S * 1000;
}

async function save(session: Session, now: number): Promise<void> {
  const remaining = SESSION_TTL_SECONDS - (now - session.createdAt) / 1000;
  if (remaining <= 0) return;
  await sessionStore().set(SESSION_KEY(session.id), JSON.stringify(session), remaining);
}

export async function createSession(tokens: TokenResult, now: number = Date.now()): Promise<Session> {
  const session: Session = {
    id: newSessionId(),
    ...identityOf(tokens),
    accessToken: tokens.accessToken,
    accessTokenExpiresAt: accessExpiry(tokens, now),
    refreshToken: tokens.refreshToken,
    idToken: tokens.idToken,
    createdAt: now,
  };
  await save(session, now);
  return session;
}

export async function destroySession(id: string): Promise<void> {
  await sessionStore().del(SESSION_KEY(id));
}

// Concurrent requests for one session share a single refresh, so a rotating
// refresh token is never redeemed twice.
const inflight = new Map<string, Promise<Session | null>>();

async function refresh(session: Session, now: number): Promise<Session | null> {
  if (!session.refreshToken) {
    await destroySession(session.id);
    return null;
  }
  try {
    const tokens = await refreshTokens(session.refreshToken);
    const next: Session = {
      ...session,
      ...identityOf(tokens),
      accessToken: tokens.accessToken,
      accessTokenExpiresAt: accessExpiry(tokens, now),
      refreshToken: tokens.refreshToken ?? session.refreshToken,
      idToken: tokens.idToken ?? session.idToken,
    };
    await save(next, now);
    return next;
  } catch (error) {
    console.warn(`[opencg/admin-ui] token refresh failed; ending the session: ${(error as Error).message}`);
    await destroySession(session.id);
    return null;
  }
}

const VALID_ID = /^[A-Za-z0-9_-]{20,128}$/;

/** The stored session as-is, without refreshing it (sign-out only needs the ID token). */
export async function peekSession(id: string | undefined): Promise<Session | null> {
  if (!id || !VALID_ID.test(id)) return null;
  const raw = await sessionStore().get(SESSION_KEY(id));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

/**
 * The live session for `id`, refreshing its access token first when it is
 * within a minute of expiry. Null when unknown, expired or refresh failed.
 */
export async function loadSession(id: string | undefined, now: number = Date.now()): Promise<Session | null> {
  const session = await peekSession(id);
  if (!session) return null;
  if (session.accessTokenExpiresAt - now > REFRESH_MARGIN_MS) return session;

  let pending = inflight.get(session.id);
  if (!pending) {
    pending = refresh(session, now).finally(() => inflight.delete(session.id));
    inflight.set(session.id, pending);
  }
  return pending;
}

export interface PendingSignin {
  codeVerifier: string;
  nonce: string;
  next: string;
}

export async function savePendingSignin(state: string, pending: PendingSignin): Promise<void> {
  await sessionStore().set(SIGNIN_KEY(state), JSON.stringify(pending), SIGNIN_TTL_SECONDS);
}

/** Read and delete a pending sign-in, so each `state` is usable once. */
export async function takePendingSignin(state: string): Promise<PendingSignin | null> {
  const store = sessionStore();
  const raw = await store.get(SIGNIN_KEY(state));
  if (!raw) return null;
  await store.del(SIGNIN_KEY(state));
  try {
    return JSON.parse(raw) as PendingSignin;
  } catch {
    return null;
  }
}

/** Only same-origin relative paths are valid post-sign-in destinations. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  // Reject control characters and backslashes browsers may normalise to "/".
  if (/[\u0000-\u001f\\]/.test(next)) return "/";
  return next;
}

export function signinPath(next: string): string {
  return `/api/auth/signin?${new URLSearchParams({ next: safeNext(next) })}`;
}

/** Secure when the public URL or the request (incl. x-forwarded-proto) is HTTPS. */
export function secureCookie(req: Request): boolean {
  if (oidcSettings().publicUrl.startsWith("https:")) return true;
  const forwarded = req.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  return (forwarded ?? new URL(req.url).protocol.replace(":", "")) === "https";
}
