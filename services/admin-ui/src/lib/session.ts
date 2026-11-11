// REPLACE-BEFORE-PROD — stopgap shared-password session for the admin UI.
//
// When OPENCG__ADMIN_UI__PASSWORD is set, every page and /api/proxy/** route
// requires a session cookie issued by /api/auth/login. The cookie is
// `<issued-at-ms>.<hex HMAC-SHA256(password, "opencg-admin:" + issued-at)>`, so
// it expires after SESSION_TTL_MS and is invalidated by changing the password.
// There is no per-user identity: replace with a real identity provider (see
// add-foundation) before any multi-user or internet-facing deployment.
//
// Uses Web Crypto only, so it runs in both the middleware (edge) and Node.

import { NextResponse } from "next/server";

export const SESSION_COOKIE = "opencg_admin_session";
export const SESSION_TTL_MS = 12 * 60 * 60 * 1000;

export function adminPassword(): string | undefined {
  const value = process.env.OPENCG__ADMIN_UI__PASSWORD;
  return value && value.length > 0 ? value : undefined;
}

const encoder = new TextEncoder();

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function issueSession(password: string, now: number = Date.now()): Promise<string> {
  return `${now}.${await hmacHex(password, `opencg-admin:${now}`)}`;
}

export async function verifySession(
  token: string | undefined,
  password: string,
  now: number = Date.now(),
): Promise<boolean> {
  if (!token) return false;
  const dot = token.indexOf(".");
  if (dot <= 0) return false;
  const issuedAt = Number(token.slice(0, dot));
  if (!Number.isSafeInteger(issuedAt) || issuedAt > now || now - issuedAt > SESSION_TTL_MS) {
    return false;
  }
  const expected = await hmacHex(password, `opencg-admin:${issuedAt}`);
  return timingSafeEqual(token.slice(dot + 1), expected);
}

// Compare a submitted password without leaking its length or prefix via timing.
export async function passwordMatches(submitted: string, password: string): Promise<boolean> {
  const [a, b] = await Promise.all([
    hmacHex("opencg-admin-compare", submitted),
    hmacHex("opencg-admin-compare", password),
  ]);
  return timingSafeEqual(a, b);
}

// The standalone server binds 0.0.0.0, so `req.url` names that host rather than
// the one the browser used; a relative Location resolves against the latter.
export function seeOther(path: string): NextResponse {
  return new NextResponse(null, { status: 303, headers: { location: path } });
}

// Only same-origin relative paths are valid post-login destinations.
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  return next;
}
