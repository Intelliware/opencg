import type { VectorSearchResult } from "../src/lib/api";
import { formatUsd } from "../src/lib/cost";
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

test("a search shows the query's embedding tokens, provider, model and estimated cost", async ({ page, run }) => {
  await page.goto("/vectors");
  await page.getByPlaceholder("Search the catalogue…").fill(`cost check ${run.id} amber-context protocol`);
  const searched = page.waitForResponse((res) => res.url().includes("/api/proxy/search/vector"));
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const body = (await (await searched).json()) as VectorSearchResult;
  expect(body, "the search response carries cost_usd").toHaveProperty("cost_usd");
  const cost = body.cost_usd === null || body.cost_usd === undefined ? "unpriced" : formatUsd(body.cost_usd);

  const header = page.getByText(/^\d+ hits?$/).locator("..");
  await expect(header).toContainText(`model: ${body.model}`);
  await expect(header).toContainText(`provider: ${body.provider}`);
  await expect(header).toContainText(`tokens_in: ${body.tokens_in}`);
  await expect(header.getByTestId("cost-value")).toContainText(cost);

  const row = page
    .getByTestId("cost-breakdown")
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: body.provider, exact: true }) })
    .filter({ has: page.getByRole("cell", { name: body.model, exact: true }) });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText(String(body.tokens_in));
  await expect(row).toContainText(cost);
});
