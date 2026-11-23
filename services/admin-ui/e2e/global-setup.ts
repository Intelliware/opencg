import { mkdirSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

import {
  ADMIN_URL,
  ALICE_STATE,
  BOB_STATE,
  OIDC_ISSUER,
  PIPELINE_URL,
  TEST_AUTH_MODE,
  USERS,
} from "./env";
import { fixture } from "./fixture-cli";
import { signInThroughIdp } from "./idp";

async function waitFor(url: string, timeoutMs = 180_000): Promise<void> {
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

/** Sign in through the Keycloak login page and save the browser's storage state. */
async function saveSignedInState(user: keyof typeof USERS, file: string): Promise<void> {
  const password = USERS[user].password();
  if (!password) throw new Error(`no password for ${user}: set the OPENCG__IDP__* values from .env.example in .env`);
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ baseURL: ADMIN_URL });
    const page = await context.newPage();
    await page.goto("/");
    await signInThroughIdp(page, USERS[user].username, password);
    await page.waitForURL(`${ADMIN_URL}/`);
    await page.getByLabel(`Signed in as ${USERS[user].username}`).first().waitFor();
    mkdirSync(path.dirname(file), { recursive: true });
    await context.storageState({ path: file });
  } finally {
    await browser.close();
  }
}

export default async function globalSetup() {
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const runId = `e2e-${stamp}-${process.pid}`;
  const uiRunId = `${runId}-ui`;

  console.log(`[e2e] run ${runId}: applying the smoke + e2e overlays (auth mode ${TEST_AUTH_MODE})`);
  fixture("up");
  const ready = [waitFor(`${PIPELINE_URL}/readyz`), waitFor(`${ADMIN_URL}/api/healthz`)];
  if (TEST_AUTH_MODE === "oidc") ready.push(waitFor(`${OIDC_ISSUER}/.well-known/openid-configuration`));
  await Promise.all(ready);

  if (TEST_AUTH_MODE === "oidc") {
    console.log(`[e2e] signing in through ${OIDC_ISSUER} as alice (admin) and bob (reader)`);
    await saveSignedInState("alice", ALICE_STATE);
    await saveSignedInState("bob", BOB_STATE);
  }

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

  return async () => {
    fixture("remove", runId);
    fixture("remove", uiRunId);
    if (process.env.E2E_KEEP_OVERLAY !== "1") fixture("restore");
  };
}
