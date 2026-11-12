// Node-only startup checks, loaded from instrumentation.ts. Refuses unsafe
// configuration (design D1, D12) and warns when the UI runs unauthenticated.
import { authMode, startupProblems } from "./lib/auth/config";

const problems = startupProblems();
if (problems.length > 0) {
  for (const problem of problems) console.error(`[opencg/admin-ui] FATAL: ${problem}`);
  // A thrown error is only logged and the server keeps serving; exit so no
  // deployment silently runs with unsafe configuration.
  process.exit(1);
}
if (authMode() === "none") {
  console.warn(
    "[opencg/admin-ui] WARNING: OPENCG__AUTH__MODE=none — the admin UI is UNAUTHENTICATED " +
      "(delete, ingest and graph-edit actions are open). Keep it on loopback, or set " +
      "OPENCG__AUTH__MODE=oidc before exposing it.",
  );
}
