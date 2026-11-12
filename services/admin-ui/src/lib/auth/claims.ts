// Map token claims to the principal and roles shown in the sidebar, with the
// same rules as the pipeline and MCP verifiers (design D6). Display only: the
// pipeline validates the access token itself on every call.

type Claims = Record<string, unknown>;

/** Decode a JWT payload without verifying it. Null for opaque tokens. */
export function decodeJwtPayload(token: string): Claims | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const json = Buffer.from(parts[1], "base64url").toString("utf8");
    const payload: unknown = JSON.parse(json);
    return payload && typeof payload === "object" ? (payload as Claims) : null;
  } catch {
    return null;
  }
}

/** Read a dotted claim path, e.g. `realm_access.roles`. */
export function claimAt(claims: Claims | null | undefined, path: string): unknown {
  let current: unknown = claims;
  for (const key of path.split(".")) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Claims)[key];
  }
  return current;
}

function asRoles(raw: unknown): string[] | undefined {
  if (Array.isArray(raw)) return raw.filter((item): item is string => typeof item === "string");
  if (typeof raw === "string") return raw.split(/[\s,]+/).filter(Boolean);
  return undefined;
}

export interface Identity {
  principal: string;
  roles: string[];
}

/** Access-token claims first, then ID-token claims; principal falls back to `sub`. */
export function identityFromClaims(
  sources: Array<Claims | null | undefined>,
  principalClaim: string,
  rolesClaim: string,
): Identity {
  const pick = (path: string) => {
    for (const claims of sources) {
      const found = claimAt(claims, path);
      if (found !== undefined && found !== null && found !== "") return found;
    }
    return undefined;
  };
  const principal = pick(principalClaim) ?? pick("sub");
  return {
    principal: typeof principal === "string" ? principal : "unknown",
    roles: asRoles(pick(rolesClaim)) ?? [],
  };
}
