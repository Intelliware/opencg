// How server components react to a pipeline 401/403: a 403 renders the
// permission-denied page (src/app/forbidden.tsx), a 401 sends the browser to
// sign in again and come back to the current path.
import { forbidden, redirect } from "next/navigation";

import { authMode } from "./config";
import { PipelineAuthError } from "./errors";
import { currentPath, currentSession } from "./request";
import { signinPath } from "./session";

/** A session younger than this whose token the pipeline rejects is a misconfiguration, not an expiry. */
const FRESH_SESSION_MS = 30_000;

export async function interruptOnAuthError(error: unknown): Promise<never> {
  if (!(error instanceof PipelineAuthError)) throw error;
  if (error.status === 403) forbidden();
  if (authMode() === "none") {
    throw new Error("The pipeline requires a token but the admin UI runs with OPENCG__AUTH__MODE=none.");
  }
  const session = await currentSession();
  if (session && Date.now() - session.createdAt < FRESH_SESSION_MS) {
    // Re-signing in would loop through the IdP; fail loudly instead.
    throw new Error(
      "The pipeline rejected a freshly issued access token; check that OPENCG__AUTH__OIDC__ISSUER " +
        "and OPENCG__AUTH__OIDC__AUDIENCE match on the admin UI and the pipeline.",
    );
  }
  redirect(signinPath(await currentPath()));
}

/** Run a server-component read, turning pipeline 401/403 into navigation. */
export async function pageRead<T>(read: () => Promise<T>): Promise<T> {
  try {
    return await read();
  } catch (error) {
    return interruptOnAuthError(error);
  }
}
