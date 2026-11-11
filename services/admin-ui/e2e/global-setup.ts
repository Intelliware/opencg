import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { request } from "@playwright/test";

import {
  ADMIN_URL,
  AUTH_STATE,
  FIXTURE_SCRIPT,
  GATED_URL,
  MAIN_PASSWORD,
  PIPELINE_URL,
} from "./env";

function fixture(...args: string[]): string {
  const result = spawnSync("bash", [FIXTURE_SCRIPT, ...args], {
    env: { ...process.env, OPENCG_E2E: "1" },
    encoding: "utf8",
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  if (result.status !== 0) {
    throw new Error(`fixture.sh ${args.join(" ")} failed (exit ${result.status}):\n${output}`);
  }
  return output;
}

async function waitFor(url: string, timeoutMs = 120_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
      last = `HTTP ${res.status}`;
    } catch (error) {
      last = String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(`${url} not ready after ${timeoutMs / 1000}s (${last}); is the stack up (make up-d)?`);
}

export default async function globalSetup() {
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const runId = `e2e-${stamp}-${process.pid}`;
  const uiRunId = `${runId}-ui`;

  console.log(`[e2e] run ${runId}: applying the smoke + e2e overlays`);
  fixture("up");
  await Promise.all([
    waitFor(`${PIPELINE_URL}/readyz`),
    waitFor(`${ADMIN_URL}/api/healthz`),
    waitFor(`${GATED_URL}/api/healthz`),
  ]);

  fixture("create", runId);
  const summary = fixture("ingest", runId);
  if (!/Ingested \d+ files \/ [1-9]\d* chunks/.test(summary)) {
    throw new Error(`fixture ingest produced no chunks:\n${summary}`);
  }
  // A second copy for ingestion.spec.ts to ingest through the UI, so that run
  // never touches the entities the other specs assert on.
  fixture("create", uiRunId);

  process.env.E2E_RUN_ID = runId;
  process.env.E2E_UI_RUN_ID = uiRunId;

  if (MAIN_PASSWORD) {
    mkdirSync(path.dirname(AUTH_STATE), { recursive: true });
    const ctx = await request.newContext({ baseURL: ADMIN_URL });
    const res = await ctx.post("/api/auth/login", {
      form: { password: MAIN_PASSWORD, next: "/" },
      maxRedirects: 0,
    });
    if (res.status() !== 303 || !res.headers()["set-cookie"]) {
      throw new Error(`could not sign in to the gated admin UI (HTTP ${res.status()})`);
    }
    await ctx.storageState({ path: AUTH_STATE });
    await ctx.dispose();
  }

  return async () => {
    fixture("remove", runId);
    fixture("remove", uiRunId);
    if (process.env.E2E_KEEP_OVERLAY !== "1") fixture("restore");
  };
}
