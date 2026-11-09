// REPLACE-BEFORE-PROD — enforces the optional shared-password gate described in
// src/lib/session.ts. With OPENCG__ADMIN_UI__PASSWORD unset this is a no-op and
// the layout shows the unauthenticated-mode banner instead.
import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, adminPassword, verifySession } from "@/lib/session";

const PUBLIC_PATHS = ["/login", "/api/auth/login", "/api/auth/logout", "/api/healthz"];

export async function middleware(req: NextRequest) {
  const password = adminPassword();
  if (!password) return NextResponse.next();

  const { pathname, search } = req.nextUrl;
  if (PUBLIC_PATHS.includes(pathname)) return NextResponse.next();

  if (await verifySession(req.cookies.get(SESSION_COOKIE)?.value, password)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "authentication required" }, { status: 401 });
  }
  const login = new URL("/login", req.url);
  login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except Next's static assets and files served from public/.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|opencg-logo.png).*)"],
};
