import { expect, test } from "./fixtures";

test("the connector list renders the git connector as supported", async ({ page }) => {
  await page.goto("/ingestion");
  const connectors = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Connectors", exact: true }),
  });
  // Innermost element holding both the card title and its status badge.
  const gitHeader = connectors
    .locator("div")
    .filter({ has: page.getByText("git", { exact: true }) })
    .filter({ has: page.getByText("supported", { exact: true }) })
    .last();
  await expect(gitHeader).toBeVisible();
});

test("Run now against the run's fixture repo reaches success", async ({ page, pipeline, run }) => {
  test.setTimeout(180_000);
  await page.goto("/ingestion");
  await page.getByLabel("Repository URL").fill(run.uiFixtureDir);
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText("Ingestion run started")).toBeVisible();

  const row = page.locator("div.grid").filter({ has: page.locator(`[title="${run.uiFixtureDir}"]`) });
  await expect(async () => {
    await page.reload();
    await expect(row.getByText("failed", { exact: true })).toHaveCount(0);
    await expect(row.getByText("succeeded", { exact: true })).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 150_000, intervals: [2_000] });
  await expect(row).toContainText(/[1-9]\d* chunks/);

  const ingested = await pipeline.runEntities(`git://opencg-smoke-${run.uiRunId}/`);
  expect(ingested.length).toBeGreaterThan(0);
});

test("a disallowed URL shows the ingestion service's reason", async ({ page }) => {
  await page.goto("/ingestion");
  const input = page.getByLabel("Repository URL");
  const submit = page.getByRole("button", { name: "Run now" });

  await input.fill("http://example.com/repo.git");
  await submit.click();
  await expect(page.locator("form").getByText(/scheme 'http' is not allowed/)).toBeVisible();

  await input.fill("/etc/opencg-e2e");
  await submit.click();
  await expect(page.locator("form").getByText(/outside the allowed local roots/)).toBeVisible();

  await input.fill("ext::sh -c touch% /tmp/pwned");
  await submit.click();
  await expect(page.locator("form").getByText(/git remote helper/)).toBeVisible();
});
