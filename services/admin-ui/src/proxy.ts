// Access gate for the admin UI (design D11). Runs on the Node.js runtime, so it
// can read the Valkey session store.
//
// - `none` mode: everything passes; the layout shows the unauthenticated banner.
// - `oidc` mode: pages without a valid session redirect to
//   /api/auth/signin?next=<path>; /api/** without a session gets 401 JSON.
//   /api/auth/*, /api/healthz and static assets stay open.
import { type NextRequest, NextResponse } from "next/server";

import { authMode, oidcSettings } from "@/lib/auth/config";
import { SIGNIN_REQUIRED } from "@/lib/auth/errors";
import { PATH_HEADER, SESSION_COOKIE, loadSession, signinPath } from "@/lib/auth/session";

export function isOpenPath(pathname: string): boolean {
  return pathname === "/api/healthz" || pathname === "/api/auth" || pathname.startsWith("/api/auth/");
}

export async function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
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
