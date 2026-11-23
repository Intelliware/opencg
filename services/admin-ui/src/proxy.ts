// Access gate for the admin UI (design D11). Runs on the Node.js runtime, so it
// can read the Valkey session store.
//
// - `none` mode: everything passes; the layout shows the unauthenticated banner.
// - `oidc` mode: pages without a valid session redirect to
//   /api/auth/signin?next=<path>; /api/** without a session gets 401 JSON.
//   /api/auth/*, /api/healthz and static assets stay open.
// - Both modes: a state-changing request to /api/** from another origin is
//   refused (403 cross_origin). The session cookie is SameSite=Lax, which still
//   lets a sibling subdomain or another localhost port send it; in `none` mode
//   there is no cookie at all, so any web page could otherwise post here.
import { type NextRequest, NextResponse } from "next/server";

import { authMode, oidcSettings } from "@/lib/auth/config";
import { SIGNIN_REQUIRED } from "@/lib/auth/errors";
import { PATH_HEADER, SESSION_COOKIE, loadSession, signinPath } from "@/lib/auth/session";

export function isOpenPath(pathname: string): boolean {
  return pathname === "/api/healthz" || pathname === "/api/auth" || pathname.startsWith("/api/auth/");
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * True for a browser request that changes state from a page on another origin.
 * Browsers send Sec-Fetch-Site (or at least Origin) on such requests; a client
 * that sends neither (curl, server-side code) is not a cross-site attacker.
 */
export function isCrossOriginWrite(req: NextRequest): boolean {
  const { pathname } = req.nextUrl;
  if (!UNSAFE_METHODS.has(req.method) || !(pathname === "/api" || pathname.startsWith("/api/"))) {
    return false;
  }
  const site = req.headers.get("sec-fetch-site");
  if (site) return site !== "same-origin" && site !== "none";
  const origin = req.headers.get("origin");
  if (!origin) return false;
  let originHost: string;
  try {
    originHost = new URL(origin).host;
  } catch {
    return true; // "null" (sandboxed iframe, file://) or garbage
  }
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (host && originHost === host) return false;
  const publicUrl = process.env.OPENCG__ADMIN_UI__PUBLIC_URL;
  return !(publicUrl && originHost === new URL(publicUrl).host);
}

export async function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (isCrossOriginWrite(req)) {
    return NextResponse.json(
      { error: "cross_origin", message: "Requests that change data must come from the admin UI itself." },
      { status: 403 },
    );
  }
  if (authMode() === "none" || isOpenPath(pathname)) return NextResponse.next();

  const isApi = pathname === "/api" || pathname.startsWith("/api/");
  let session;
  try {
    session = await loadSession(req.cookies.get(SESSION_COOKIE)?.value);
  } catch (error) {
    console.error(`[opencg/admin-ui] session store unavailable: ${(error as Error).message}`);
    return isApi
      ? NextResponse.json({ error: "session_store_unavailable" }, { status: 503 })
      : new NextResponse("The admin UI session store (Valkey) is unavailable.\n", {
          status: 503,
          headers: { "content-type": "text/plain; charset=utf-8" },
        });
  }

  if (session) {
    // Tell server components which path to return to if the pipeline later
    // rejects the token.
    const headers = new Headers(req.headers);
    headers.set(PATH_HEADER, `${pathname}${search}`);
    return NextResponse.next({ request: { headers } });
  }
  if (isApi) {
    return NextResponse.json(
      { error: SIGNIN_REQUIRED, message: "Sign in to use the admin UI." },
      { status: 401 },
    );
  }
  // Absolute against the public URL: the standalone server's req.url names its
  // bind address, and the proxy layer rejects a relative Location.
  return NextResponse.redirect(new URL(signinPath(`${pathname}${search}`), oidcSettings().publicUrl), 307);
}

export const config = {
  // Everything except Next's static assets and files served from public/.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|opencg-logo.png).*)"],
};
