// Client-side handling of /api/proxy/** auth responses: 401 sends the browser
// to sign in and come back here; 403 yields the permission-denied message.
import { permissionDeniedMessage, type AuthErrorBody } from "@/lib/auth/errors";

export type ProxyAuthOutcome =
  | { kind: "ok" }
  | { kind: "signin" }
  | { kind: "denied"; action: string; message: string };

export function signinHref(location: { pathname: string; search: string }): string {
  return `/api/auth/signin?${new URLSearchParams({ next: `${location.pathname}${location.search}` })}`;
}

/** Inspect a proxy response; on 401 also starts the sign-in redirect. */
export async function checkProxyAuth(
  res: Response,
  fallbackAction: string,
  navigate: (href: string) => void = (href) => window.location.assign(href),
): Promise<ProxyAuthOutcome> {
  if (res.status === 401) {
    navigate(signinHref(window.location));
    return { kind: "signin" };
  }
  if (res.status === 403) {
    const body = (await res.clone().json().catch(() => ({}))) as Partial<AuthErrorBody>;
    const action = body.action ?? fallbackAction;
    return { kind: "denied", action, message: permissionDeniedMessage(action) };
  }
  return { kind: "ok" };
}
