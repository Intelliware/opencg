import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

// The concept detail header; neighbour links carry the same title attribute.
const heading = (scope: Page | Locator, name: string) => scope.locator(`p[title="${name}"]`);

test("graph tabs are in the expected order", async ({ page }) => {
  await page.goto("/graph");
  await expect(page.locator('a[href^="/graph?tab="]')).toHaveText([
    "Map",
    "Concepts",
    "Candidate review",
    "Vocabulary",
  ]);
});

test("concept search opens the run's concept detail", async ({ page, pipeline, run }) => {
  const { catalogue } = await pipeline.runConcepts(run.id);
  await page.goto("/graph?tab=concepts");
  await page.getByPlaceholder("Search concepts", { exact: true }).fill(run.id);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`search=${run.id}`));

  await expect(page.getByRole("link", { name: new RegExp(`Context windows ${run.id}\\b`) })).toBeVisible();
  await page.getByRole("link", { name: new RegExp(`Smoke catalogue ${run.id}\\b`) }).click();
  await expect(page).toHaveURL(new RegExp(`concept_id=${catalogue.concept_id}`));
  await expect(heading(page, catalogue.name)).toBeVisible();
  await expect(page.getByRole("tab", { name: /^Candidate \d+$/ })).toBeVisible();
});

test("the map's detail panel follows concept search", async ({ page, pipeline, run }) => {
  const { catalogue, context } = await pipeline.runConcepts(run.id);
  await page.goto(`/graph?tab=map&focus=${catalogue.concept_id}&candidates=1`);
  const panel = page.locator("aside");
  await expect(heading(panel, catalogue.name)).toBeVisible();
  await expect(page.getByRole("button", { name: "Candidates: on" })).toBeVisible();

  await page.getByLabel("Search concepts").fill(context.name);
  await page.getByRole("list").getByRole("button", { name: new RegExp(`^${context.name}`) }).click();
  await expect(heading(panel, context.name)).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`focus=${context.concept_id}`));
});

test("promote one run candidate and reject the other", async ({ page, pipeline, run }) => {
  const candidates = await pipeline.runCandidates(run.id);
  const promote = candidates.find((edge) => edge.type === "related_to");
  const reject = candidates.find((edge) => edge.type === "derived_from");
  expect(promote && reject, "the chat stub's two run candidates").toBeTruthy();
  const runEdgeIds = new Set(candidates.map((edge) => edge.edge_id));
  const othersBefore = (await pipeline.edges("candidate"))
    .filter((edge) => !runEdgeIds.has(edge.edge_id))
    .map((edge) => edge.edge_id);

  const rowFor = (edge: typeof promote) =>
    page.locator("div.grid").filter({ hasText: `${edge!.from_concept_id} → ${edge!.to_concept_id}` });

  await page.goto("/graph?tab=candidates");
  await rowFor(promote).getByRole("button", { name: "Promote" }).click();
  await expect(rowFor(promote)).toHaveCount(0);
  await rowFor(reject).getByRole("button", { name: "Delete" }).click();
  await expect(rowFor(reject)).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Candidate review" })).toBeVisible();
  await expect(rowFor(promote)).toHaveCount(0);
  await expect(rowFor(reject)).toHaveCount(0);

  // The edge list API omits tombstoned edges, so check through the concept.
  const { catalogue } = await pipeline.runConcepts(run.id);
  const detail = await pipeline.concept(catalogue.concept_id);
  const ids = (items: readonly { edge: { edge_id: string } }[]) => items.map((item) => item.edge.edge_id);
  expect(ids(detail.neighbours_confirmed)).toEqual([promote!.edge_id]);
  expect(ids(detail.neighbours_candidate)).toEqual([]);

  await page.goto(`/graph?concept_id=${catalogue.concept_id}`);
  await expect(page.getByRole("tab", { name: "Confirmed 1" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Candidate 0" })).toBeVisible();

  const stillCandidates = new Set((await pipeline.edges("candidate")).map((edge) => edge.edge_id));
  expect(othersBefore.filter((id) => !stillCandidates.has(id)), "other runs' candidates untouched").toEqual(
    [],
  );
});

test("add and edit a vocabulary entry", async ({ page, pipeline, run }) => {
  const name = run.id.replace(/-/g, "_");
  const othersBefore = (await pipeline.vocabulary()).filter((item) => item.name !== name);

  await page.goto("/graph?tab=vocabulary");
  await page.getByLabel("Relationship name").fill(name);
  await page.getByLabel("Relationship description").fill("Added by the e2e suite");
  await page.getByRole("button", { name: "Add type" }).click();

  const description = page.getByLabel(`${name} description`);
  await expect(description).toHaveValue("Added by the e2e suite");
  const row = page.locator("div.grid").filter({ has: description });
  await description.fill("Edited by the e2e suite");
  await row.getByRole("button", { name: "Save" }).click();
  await expect
    .poll(async () => (await pipeline.vocabulary()).find((item) => item.name === name)?.description)
    .toBe("Edited by the e2e suite");

  await page.reload();
  await expect(page.getByLabel(`${name} description`)).toHaveValue("Edited by the e2e suite");

  // Vocabulary entries can't be deleted; deprecate this run's one so the
  // extractor's vocabulary isn't left with e2e names.
  await page.locator("div.grid").filter({ has: page.getByLabel(`${name} description`) })
    .getByRole("button", { name: "Deprecate" })
    .click();
  await expect
    .poll(async () => (await pipeline.vocabulary()).find((item) => item.name === name)?.deprecated_at)
    .toBeTruthy();

  const othersAfter = (await pipeline.vocabulary()).filter((item) => item.name !== name);
  expect(othersAfter, "other vocabulary entries untouched").toEqual(othersBefore);
});
