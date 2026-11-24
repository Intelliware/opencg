// Runs tests/smoke/fixture.sh (overlays, fixture copies, Postgres queries) with
// the e2e overlay and the suite's auth mode.
import { spawnSync } from "node:child_process";

import { FIXTURE_SCRIPT, TEST_AUTH_MODE } from "./env";

export function fixture(...args: string[]): string {
  const result = spawnSync("bash", [FIXTURE_SCRIPT, ...args], {
    env: { ...process.env, OPENCG_E2E: "1", OPENCG_TEST_AUTH_MODE: TEST_AUTH_MODE },
    encoding: "utf8",
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  if (result.status !== 0) {
    throw new Error(`fixture.sh ${args[0]} failed (exit ${result.status}):\n${output}`);
  }
  return output;
}

/** Rows of a Postgres query, each split on "|" (psql -tA). */
export function sql(query: string): string[][] {
  return fixture("sql", query)
    .split("\n")
    .filter((line) => line.length > 0)
    .map((line) => line.split("|"));
}
