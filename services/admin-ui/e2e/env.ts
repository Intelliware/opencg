// Settings for the e2e suite, resolved the same way as tests/smoke/lib.sh:
// environment first, then the repo's .env, then the compose default.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(here, "../../..");
export const FIXTURE_SCRIPT = path.join(REPO_ROOT, "tests/smoke/fixture.sh");
export const AUTH_STATE = path.join(here, ".auth/state.json");

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
export const GATED_URL =
  process.env.E2E_GATED_URL ??
  `http://localhost:${setting("OPENCG__ADMIN_UI_GATED__HOST_PORT", "3001")}`;
export const PIPELINE_URL =
  process.env.PIPELINE_URL ?? `http://localhost:${setting("OPENCG__PIPELINE__HOST_PORT", "8000")}`;

/** Password of the always-gated `admin-ui-gated` instance (docker-compose.e2e.yml). */
export const GATE_PASSWORD = setting("OPENCG__E2E__GATE_PASSWORD", "e2e-gate-password");
/** Set when the main admin UI itself has the access gate on. */
export const MAIN_PASSWORD = setting("OPENCG__ADMIN_UI__PASSWORD") || undefined;
