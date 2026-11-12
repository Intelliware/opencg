// POST /api/auth/signout — delete the server-side session, clear the cookie and
// send the browser to the IdP's end-session endpoint (RP-initiated logout) with
// `id_token_hint` and a post-logout redirect to the admin UI root.
import { type NextRequest, NextResponse } from "next/server";

import { authMode, oidcSettings } from "@/lib/auth/config";
import { endSessionUrl } from "@/lib/auth/oidc";
import { SESSION_COOKIE, destroySession, peekSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const root = new NextResponse(null, { status: 303, headers: { location: "/" } });
  if (authMode() === "none") return root;

  const id = req.cookies.get(SESSION_COOKIE)?.value;
  const session = await peekSession(id).catch(() => null);
  if (id) await destroySession(id).catch(() => undefined);

  let target: URL | null = null;
  try {
    target = await endSessionUrl({
      idTokenHint: session?.idToken,
      postLogoutRedirectUri: `${oidcSettings().publicUrl}/`,
    });
  } catch (error) {
    console.warn(`[opencg/admin-ui] end-session URL unavailable: ${(error as Error).message}`);
  }
  const res = target ? NextResponse.redirect(target, 303) : root;
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
