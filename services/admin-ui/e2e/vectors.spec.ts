import { expect, test } from "./fixtures";

test("the run's unique phrase returns a current-run hit with score and snippet", async ({ page, run }) => {
  await page.goto("/vectors");
  // The README chunk carries the run ID, so it ranks first among the
  // otherwise identical fixture copies left by earlier runs.
  await page.getByPlaceholder("Search the catalogue…").fill(`Smoke run: ${run.id} amber-context protocol`);
  await page.locator('input[name="top_k"]').fill("100");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page.getByText(/^\d+ hits?$/)).toBeVisible();
  const hit = page.locator("article").filter({ hasText: `${run.prefix}README.md` }).first();
  await expect(hit).toBeVisible();
  await expect(hit.getByText(/^\d\.\d{4}$/)).toBeVisible();
  await expect(hit.locator("p")).toContainText("amber-context protocol");
});

test("an empty query sends no request and shows no results", async ({ page }) => {
  await page.goto("/vectors");
  const searches: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/proxy/search/vector")) searches.push(req.url());
  });
  await page.getByPlaceholder("Search the catalogue…").fill("   ");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page.getByRole("button", { name: "Search", exact: true })).toBeEnabled();
  await expect(page.getByText(/^\d+ hits?$/)).toHaveCount(0);
  await expect(page.locator("article")).toHaveCount(0);
  expect(searches).toEqual([]);
});
