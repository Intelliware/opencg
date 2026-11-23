import type { Page } from "@playwright/test";

import { ADMIN_URL, BOB_STATE, OIDC_ISSUER, TEST_AUTH_MODE, USERS } from "./env";
import { sql } from "./fixture-cli";
import { expect, test } from "./fixtures";
import { signInThroughIdp } from "./idp";

const SIGNED_OUT = { cookies: [], origins: [] };
const onIdp = (url: URL) => url.href.startsWith(`${OIDC_ISSUER}/`);
/** Single-quoted SQL literal for values the suite generated itself. */
const lit = (value: string) => `'${value.replace(/'/g, "''")}'`;

async function expectIdpLoginPage(page: Page) {
  await expect(page).toHaveURL(onIdp);
  await expect(page.locator("#username")).toBeVisible();
}

async function proxiedStatus(page: Page): Promise<number> {
  const res = await page.request.post(`${ADMIN_URL}/api/proxy/search/vector`, {
    data: { query: "amber-context protocol", top_k: 1 },
  });
  return res.status();
}

test.describe("OIDC sign-in against the bundled Keycloak", () => {
  test.skip(TEST_AUTH_MODE !== "oidc", "OPENCG_TEST_AUTH_MODE=none: the stack runs without an IdP");

  test.describe("signed out", () => {
    test.use({ storageState: SIGNED_OUT });

    test("an unauthenticated visit is redirected to the IdP and back", async ({ page }) => {
      expect(await proxiedStatus(page), "proxy routes need a session").toBe(401);
      await page.goto("/graph");
      await expectIdpLoginPage(page);

      await signInThroughIdp(page, USERS.alice.username, USERS.alice.password());
      await expect(page).toHaveURL(`${ADMIN_URL}/graph`);
      await expect(page.getByRole("heading", { name: "Knowledge graph", exact: true })).toBeVisible();
      await expect(page.getByLabel("Signed in as alice").first()).toBeVisible();
      await expect(page.getByText("Unauthenticated mode")).toHaveCount(0);
      expect(await proxiedStatus(page), "proxy routes work with a session").toBe(200);
    });

    test("a wrong password is refused by the IdP", async ({ page }) => {
      await page.goto("/ingestion");
      await signInThroughIdp(page, USERS.alice.username, "not-the-password");
      await expectIdpLoginPage(page);
      await expect(page.getByText("Invalid username or password.")).toBeVisible();
      expect(await proxiedStatus(page), "no admin UI session after a refused sign-in").toBe(401);
    });

    test("sign-out ends the IdP session and the next visit asks to sign in again", async ({ page }) => {
      await page.goto("/ingestion");
      await signInThroughIdp(page, USERS.alice.username, USERS.alice.password());
      await expect(page).toHaveURL(`${ADMIN_URL}/ingestion`);

      await page.getByRole("button", { name: "Sign out" }).filter({ visible: true }).click();
      // RP-initiated logout at the IdP, back to the admin UI root, which has no
      // session any more and so starts a new sign-in at the IdP.
      await expectIdpLoginPage(page);
      expect(await proxiedStatus(page), "the admin UI session is gone").toBe(401);

      await page.goto(`${ADMIN_URL}/ingestion`);
      await expectIdpLoginPage(page);
    });
  });

  test.describe("as bob (reader)", () => {
    test.use({ storageState: BOB_STATE });

    test("a reader is denied a tombstone; the entity is unchanged and the denial audited", async ({
      page,
      pipeline,
      run,
    }) => {
      // A document (not a chunk): no other spec tombstones those.
      const [[entityId]] = sql(`
        SELECT entity_id FROM opencg.entity
        WHERE source_uri LIKE ${lit(`${run.prefix}%`)} AND parent_entity_id IS NULL
        ORDER BY source_uri LIMIT 1`);
      expect(entityId, "a document from this run").toBeTruthy();

      await page.goto(`/entities/${entityId}`);
      await expect(page.getByLabel("Signed in as bob").first()).toBeVisible();
      page.once("dialog", (dialog) => dialog.accept());
      await page.getByRole("button", { name: "Tombstone", exact: true }).click();
      await expect(
        page.getByRole("alert").filter({ hasText: "You don't have permission to tombstone this entity." }),
      ).toBeVisible();
      await expect(page.getByText(/^Tombstoned at /)).toHaveCount(0);

      expect((await pipeline.entity(entityId)).tombstoned_at ?? null).toBeNull();
      const denials = sql(`
        SELECT decision, reason FROM opencg.access_audit_log
        WHERE principal = 'bob' AND action = 'entity.tombstone' AND resource = ${lit(entityId)}`);
      expect(denials, "access_audit_log rows for bob's tombstone").toEqual([["deny", "insufficient_role"]]);
    });
  });

  test("an admin action is attributed to the signed-in user", async ({ page, pipeline, run }) => {
    const name = `${run.id.replace(/-/g, "_")}_auth`;
    await page.goto("/graph?tab=vocabulary");
    await expect(page.getByLabel("Signed in as alice").first()).toBeVisible();
    await page.getByLabel("Relationship name").fill(name);
    await page.getByLabel("Relationship description").fill("Added by the e2e auth spec");
    await page.getByRole("button", { name: "Add type" }).click();
    const description = page.getByLabel(`${name} description`);
    await expect(description).toHaveValue("Added by the e2e auth spec");

    // Deprecate it again, so the extractor's vocabulary keeps no e2e names.
    await page.locator("div.grid").filter({ has: description }).getByRole("button", { name: "Deprecate" }).click();
    await expect
      .poll(async () => (await pipeline.vocabulary()).find((item) => item.name === name)?.deprecated_at)
      .toBeTruthy();

    const actors = sql(`
      SELECT DISTINCT actor FROM opencg.graph_audit_log
      WHERE target_kind = 'vocab' AND target_id = ${lit(name)}`);
    expect(actors, "graph_audit_log actor for the vocabulary writes").toEqual([["alice"]]);
    const allowed = sql(`
      SELECT principal, decision FROM opencg.access_audit_log
      WHERE action = 'vocab.write' AND resource = ${lit(name)}`);
    expect(allowed, "access_audit_log row for the deprecation").toEqual([["alice", "allow"]]);
  });
});

test.describe("in unauthenticated mode", () => {
  test.skip(TEST_AUTH_MODE !== "none", "OPENCG_TEST_AUTH_MODE=oidc: the admin UI requires sign-in");

  test("every page shows the unauthenticated-mode banner and no sign-out", async ({ page }) => {
    for (const path of ["/", "/graph", "/ingestion"]) {
      await page.goto(path);
      await expect(page.getByRole("status").filter({ hasText: "Unauthenticated mode" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
    }
  });
});
