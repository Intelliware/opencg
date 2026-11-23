// Pipeline auth failures (401/403) and how each caller surfaces them.

export const PERMISSION_DENIED = "permission_denied";
export const SIGNIN_REQUIRED = "signin_required";

export class PipelineAuthError extends Error {
  constructor(
    readonly status: 401 | 403,
    /** What the user tried to do, e.g. "tombstone this entity". */
    readonly action: string,
  ) {
    super(status === 403 ? permissionDeniedMessage(action) : "Sign-in required");
    this.name = "PipelineAuthError";
  }
}

export function permissionDeniedMessage(action: string): string {
  return `You don't have permission to ${action}.`;
}

export interface AuthErrorBody {
  error: typeof PERMISSION_DENIED | typeof SIGNIN_REQUIRED;
  action?: string;
  message: string;
}

/** JSON body a `/api/proxy/**` route returns for a pipeline 401/403. */
export function authErrorBody(status: 401 | 403, action: string): AuthErrorBody {
  return status === 403
    ? { error: PERMISSION_DENIED, action, message: permissionDeniedMessage(action) }
    : { error: SIGNIN_REQUIRED, message: "Your session has ended. Sign in again." };
}

export function authErrorResponse(error: PipelineAuthError): Response {
  return Response.json(authErrorBody(error.status, error.action), { status: error.status });
}
