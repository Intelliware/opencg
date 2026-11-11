import { expect, test } from "./fixtures";

const isCodeChunk = (uri: string) => uri.includes("#symbol=");

test("browse, paginate, open detail and lineage, then tombstone a run chunk", async ({
  page,
  pipeline,
  run,
}) => {
  const entities = await pipeline.runEntities(run.prefix);
  const chunk = entities.find((item) => isCodeChunk(item.source_uri) && !item.tombstoned_at);
  expect(chunk, "an untombstoned code chunk from this run").toBeTruthy();
  const parentUri = chunk!.source_uri.split("#")[0];

  await test.step("filter to git and find the run's chunk", async () => {
    await page.goto("/entities");
    await page.getByPlaceholder("source (e.g. git)").fill("git");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page).toHaveURL(/[?&]source=git\b/);
    // Newest first, so the run's entities lead the list.
    await expect(page.locator(`a[href="/entities/${chunk!.entity_id}"]`)).toBeVisible();
  });

  await test.step("paginate", async () => {
    await page.goto("/entities?source=git&limit=2");
    await expect(page.getByText(/^1–2 of \d+$/)).toBeVisible();
    await page.getByRole("link", { name: "next →" }).click();
    await expect(page).toHaveURL(/offset=2/);
    await expect(page.getByText(/^3–\d+ of \d+$/)).toBeVisible();
    await page.getByRole("link", { name: "← prev" }).click();
    await expect(page.getByText(/^1–2 of \d+$/)).toBeVisible();
  });

  await test.step("open detail and lineage", async () => {
    await page.goto("/entities?source=git");
    await page.locator(`a[href="/entities/${chunk!.entity_id}"]`).click();
    await expect(page).toHaveURL(new RegExp(`/entities/${chunk!.entity_id}$`));
    await expect(page.getByText(chunk!.source_uri, { exact: true })).toBeVisible();
    const lineage = page.locator("section").filter({ has: page.getByRole("heading", { name: "Lineage" }) });
    await expect(lineage).toBeVisible();
    const parentLink = lineage.getByRole("link").first();
    await expect(parentLink).toContainText(parentUri.split("/").pop()!);
    await parentLink.click();
    await expect(page.getByText(parentUri, { exact: true })).toBeVisible();
    await page.locator(`section a[href="/entities/${chunk!.entity_id}"]`).click();
    await expect(page).toHaveURL(new RegExp(`/entities/${chunk!.entity_id}$`));
  });

  await test.step("tombstone it", async () => {
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Tombstone", exact: true }).click();
    await expect(page.getByText(/^Tombstoned at /)).toBeVisible();
    await expect(page.getByRole("button", { name: "Tombstone", exact: true })).toHaveCount(0);
    expect((await pipeline.entity(chunk!.entity_id)).tombstoned_at).toBeTruthy();

    await page.goto("/entities?source=git");
    await expect(page.locator(`a[href="/entities/${chunk!.entity_id}"]`)).toContainText("RIP");
  });
});

test("a tombstoned chunk no longer appears in vector search", async ({ page, pipeline, run }) => {
  const entities = await pipeline.runEntities(run.prefix);
  const chunks = entities.filter((item) => isCodeChunk(item.source_uri));
  const victim = chunks.find((item) => !item.tombstoned_at) ?? chunks[0];
  const parentUri = victim.source_uri.split("#")[0];
  const search = async () =>
    (await pipeline.vectorSearch("select context fragments", { source_uri: parentUri })).hits.map(
      (hit) => hit.entity_id,
    );

  if (!victim.tombstoned_at) {
    // Prove it is searchable first, then tombstone it through the UI.
    expect(await search()).toContain(victim.entity_id);
    await page.goto(`/entities/${victim.entity_id}`);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Tombstone", exact: true }).click();
    await expect(page.getByText(/^Tombstoned at /)).toBeVisible();
  }

  expect(await search()).not.toContain(victim.entity_id);
});
