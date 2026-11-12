// Per-request auth helpers for server components and route handlers.
import { cookies, headers } from "next/headers";
import { cache } from "react";

import { authMode } from "./config";
import { PATH_HEADER, SESSION_COOKIE, loadSession, type Session } from "./session";

/** The signed-in session, or null (always null in `none` mode). */
export const currentSession = cache(async (): Promise<Session | null> => {
  if (authMode() === "none") return null;
  const id = (await cookies()).get(SESSION_COOKIE)?.value;
  return loadSession(id);
});

/** `Authorization` header for pipeline calls; empty in `none` mode. */
export async function pipelineAuthHeaders(): Promise<Record<string, string>> {
  const session = await currentSession();
  return session ? { authorization: `Bearer ${session.accessToken}` } : {};
}

export async function currentPath(): Promise<string> {
  return (await headers()).get(PATH_HEADER) ?? "/";
}
