// Settings for the e2e suite, resolved the same way as tests/smoke/lib.sh:
// environment first, then the repo's .env, then the compose default.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(here, "../../..");
export const FIXTURE_SCRIPT = path.join(REPO_ROOT, "tests/smoke/fixture.sh");
/** Signed-in browser storage states written by global setup (oidc mode). */
export const ALICE_STATE = path.join(here, ".auth/alice.json");
export const BOB_STATE = path.join(here, ".auth/bob.json");

function dotenv(): Record<string, string> {
  try {
    const values: Record<string, string> = {};
    for (const line of readFileSync(path.join(REPO_ROOT, ".env"), "utf8").split("\n")) {
      const match = /^([A-Z0-9_]+)=(.*)$/.exec(line);
      if (match) values[match[1]] = match[2];
    }
    return values;
  } catch {
    return {};
  }
}

const fromFile = dotenv();

export function setting(key: string, fallback = ""): string {
  return process.env[key] || fromFile[key] || fallback;
}

export const ADMIN_URL =
  process.env.E2E_BASE_URL ?? `http://localhost:${setting("OPENCG__ADMIN_UI__HOST_PORT", "3000")}`;
export const PIPELINE_URL =
  process.env.PIPELINE_URL ?? `http://localhost:${setting("OPENCG__PIPELINE__HOST_PORT", "8000")}`;

/**
 * The auth mode the suite runs the stack under: `OPENCG_TEST_AUTH_MODE`
 * (default `oidc`, as for `make smoke`). Global setup applies the matching
 * overlays (tests/smoke/lib.sh), whatever `OPENCG__AUTH__MODE` in .env says.
 */
export const TEST_AUTH_MODE: "oidc" | "none" = (() => {
  const mode = process.env.OPENCG_TEST_AUTH_MODE || "oidc";
  if (mode !== "oidc" && mode !== "none") {
    throw new Error(`OPENCG_TEST_AUTH_MODE must be "oidc" or "none", got "${mode}"`);
  }
  return mode;
})();

/** The bundled Keycloak's public issuer (docker-compose.oidc.yml). */
export const OIDC_ISSUER = `${setting(
  "OPENCG__KEYCLOAK__PUBLIC_URL",
  `http://localhost:${setting("OPENCG__KEYCLOAK__HOST_PORT", "8380")}`,
).replace(/\/+$/, "")}/realms/opencg`;

/** Dev users imported into the bundled realm (.env.example, dev-only values). */
export const USERS = {
  alice: { username: "alice", password: () => setting("OPENCG__IDP__ALICE_PASSWORD") },
  bob: { username: "bob", password: () => setting("OPENCG__IDP__BOB_PASSWORD") },
} as const;

/** Client-credentials account for direct pipeline calls (roles admin, reader). */
export const SERVICE_CLIENT = {
  id: "opencg-smoke",
  secret: () => setting("OPENCG__SMOKE__CLIENT_SECRET"),
  principal: "service-account-opencg-smoke",
};
