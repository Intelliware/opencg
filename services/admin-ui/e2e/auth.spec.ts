import { GATE_PASSWORD, GATED_URL, MAIN_PASSWORD } from "./env";
import { expect, test } from "./fixtures";

test.describe("with the access gate enabled", () => {
  test.use({ baseURL: GATED_URL, storageState: { cookies: [], origins: [] } });

  test("an unauthenticated visit redirects to login and proxy calls get 401", async ({ page, request }) => {
    await page.goto("/graph");
    await expect(page).toHaveURL(/\/login\?next=%2Fgraph$/);
    await expect(page.getByRole("heading", { name: "Sign in to openCG" })).toBeVisible();

    const proxied = await request.post(`${GATED_URL}/api/proxy/search/vector`, {
      data: { query: "amber-context protocol", top_k: 1 },
    });
    expect(proxied.status()).toBe(401);
    const health = await request.get(`${GATED_URL}/api/healthz`);
    expect(health.status()).toBe(200);
  });

  test("a wrong password is refused and the right one signs in and out", async ({ page }) => {
    await page.goto("/ingestion");
    await page.getByLabel("Access password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Incorrect password." })).toBeVisible();
    await expect(page).toHaveURL(/\/login\?/);

    await page.getByLabel("Access password").fill(GATE_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(new RegExp(`^${GATED_URL}/ingestion$`));
    await expect(page.getByRole("heading", { name: "Ingestion", exact: true })).toBeVisible();
    await expect(page.getByText("Unauthenticated mode")).toHaveCount(0);

    const proxied = await page.request.post("/api/proxy/search/vector", {
      data: { query: "amber-context protocol", top_k: 1 },
    });
    expect(proxied.status()).toBe(200);

    await page.getByRole("button", { name: "Sign out" }).filter({ visible: true }).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/ingestion");
    await expect(page).toHaveURL(/\/login\?next=%2Fingestion$/);
  });
});

test.describe("with the access gate disabled", () => {
  test.skip(Boolean(MAIN_PASSWORD), "the main admin UI has OPENCG__ADMIN_UI__PASSWORD set");

  test("every page shows the unauthenticated-mode banner and no sign-out", async ({ page }) => {
    for (const path of ["/", "/graph", "/ingestion"]) {
      await page.goto(path);
      await expect(page.getByRole("status").filter({ hasText: "Unauthenticated mode" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
    }
  });
});
