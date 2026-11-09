import { expect, test } from "./fixtures";

test("a retrieval issued through the pipeline appears in /queries with tokens and fragments", async ({
  page,
  pipeline,
  run,
}) => {
  const correlationId = `${run.id}-queries`;
  const query = `amber-context protocol ${run.id}`;
  await pipeline.retrieve(correlationId, query);
  const audit = await pipeline.auditFor(correlationId);

  await page.goto("/queries");
  const row = page.locator(`a[href="/queries/${audit.id}"]`);
  await expect(row).toContainText(query);
  await expect(row).toContainText(audit.tool);
  await expect(row).toContainText(`${audit.latency_ms} ms`);

  await row.click();
  await expect(page).toHaveURL(new RegExp(`/queries/${audit.id}$`));
  await expect(page.getByRole("heading", { name: `Audit #${audit.id}` })).toBeVisible();
  await expect(page.getByText(correlationId, { exact: true })).toBeVisible();
  await expect(page.getByText(`↑ ${audit.tokens_in}`, { exact: true })).toBeVisible();
  await expect(page.getByText(`↓ ${audit.tokens_out}`, { exact: true })).toBeVisible();
  await expect(
    page.getByText(
      `Candidates (${audit.candidate_ids.length}) → final (${audit.final_entity_ids.length})`,
    ),
  ).toBeVisible();
  expect(audit.final_entity_ids.length).toBeGreaterThan(0);
  for (const entityId of audit.final_entity_ids) {
    await expect(page.getByText(entityId, { exact: true })).toBeVisible();
  }
});
