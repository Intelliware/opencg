// GET /api/auth/signin?next=/path — start the authorization code flow with
// PKCE (S256), `state` and `nonce` (design D11). `next` must be a same-origin
// path; anything else falls back to "/".
import { NextResponse } from "next/server";

import { authMode, callbackUrl, oidcSettings } from "@/lib/auth/config";
import { startAuthorization } from "@/lib/auth/oidc";
import {
  SIGNIN_COOKIE,
  SIGNIN_TTL_SECONDS,
  safeNext,
  savePendingSignin,
  secureCookie,
} from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const next = safeNext(new URL(req.url).searchParams.get("next"));
  // The standalone server binds 0.0.0.0, so redirect with a relative Location.
  if (authMode() === "none") return new NextResponse(null, { status: 303, headers: { location: next } });

  const settings = oidcSettings();
  const start = await startAuthorization(settings, callbackUrl(settings));
  await savePendingSignin(start.state, { codeVerifier: start.codeVerifier, nonce: start.nonce, next });

  const res = NextResponse.redirect(start.url, 303);
  // Binds the flow to this browser: the callback's `state` must match it.
  res.cookies.set(SIGNIN_COOKIE, start.state, {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookie(req),
    path: "/api/auth",
    maxAge: SIGNIN_TTL_SECONDS,
  });
  return res;
}
