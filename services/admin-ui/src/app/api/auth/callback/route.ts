// GET /api/auth/callback — the IdP redirect target. Checks `state` against the
// sign-in cookie, exchanges the code server-side (through the internal issuer
// URL) and stores the tokens in a new Valkey session.
import { type NextRequest, NextResponse } from "next/server";

import { authMode, callbackUrl, oidcSettings } from "@/lib/auth/config";
import { exchangeCode } from "@/lib/auth/oidc";
import {
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  SIGNIN_COOKIE,
  createSession,
  secureCookie,
  takePendingSignin,
} from "@/lib/auth/session";

export const dynamic = "force-dynamic";

function failed(message: string, status = 400): NextResponse {
  const res = new NextResponse(
    `Sign-in failed: ${message}\n\nStart again at /api/auth/signin.\n`,
    { status, headers: { "content-type": "text/plain; charset=utf-8" } },
  );
  res.cookies.delete({ name: SIGNIN_COOKIE, path: "/api/auth" });
  return res;
}

export async function GET(req: NextRequest) {
  if (authMode() === "none") return new NextResponse(null, { status: 303, headers: { location: "/" } });

  const params = req.nextUrl.searchParams;
  const state = params.get("state");
  const cookieState = req.cookies.get(SIGNIN_COOKIE)?.value;
  if (!state || !cookieState || state !== cookieState) {
    return failed("the sign-in state does not match this browser.");
  }
  const pending = await takePendingSignin(state);
  if (!pending) return failed("the sign-in request expired.");
  const idpError = params.get("error");
  if (idpError) return failed(`the identity provider returned "${idpError}".`);

  const settings = oidcSettings();
  const redirectUri = callbackUrl(settings);
  // req.url names the bind address in the standalone server; rebuild the URL
  // the IdP actually redirected to from the public origin.
  const currentUrl = new URL(`${redirectUri}${req.nextUrl.search}`);
  let tokens;
  try {
    tokens = await exchangeCode(
      currentUrl,
      { codeVerifier: pending.codeVerifier, state, nonce: pending.nonce },
      redirectUri,
    );
  } catch (error) {
    console.warn(`[opencg/admin-ui] code exchange failed: ${(error as Error).message}`);
    return failed("the authorization code could not be exchanged.", 502);
  }
  const session = await createSession(tokens);

  const res = new NextResponse(null, { status: 303, headers: { location: pending.next } });
  res.cookies.set(SESSION_COOKIE, session.id, {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookie(req),
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  res.cookies.delete({ name: SIGNIN_COOKIE, path: "/api/auth" });
  return res;
}
