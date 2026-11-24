import type { Page } from "@playwright/test";
import type { ProviderUsage } from "@opencg/shared";
import { formatUsd, summarizeCost } from "../src/lib/cost";
import { expect, test } from "./fixtures";

/** The breakdown row whose provider and model cells match exactly ("ollama" must not match "ollama-cloud"). */
function providerRow(page: Page, usage: ProviderUsage) {
  return page
    .getByTestId("cost-breakdown")
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: usage.provider, exact: true }) })
    .filter({ has: page.getByRole("cell", { name: usage.model, exact: true }) });
}

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

test("a live retrieval shows its estimated cost on /queries and a per-provider breakdown on its detail page", async ({
  page,
  pipeline,
  run,
}) => {
  const correlationId = `${run.id}-queries-cost`;
  await pipeline.retrieve(correlationId, `cost of the amber-context protocol ${run.id}`);
  const audit = await pipeline.auditFor(correlationId);

  const providers = audit.usage_by_provider ?? [];
  expect(audit.estimated_cost_usd, "the audit row records an estimated cost").toEqual(expect.any(Number));
  expect(providers.length, "the audit row records per-provider usage").toBeGreaterThan(0);
  const summary = summarizeCost(audit.estimated_cost_usd, providers);
  expect(summary.kind).not.toBe("missing");
  const total = formatUsd(summary.kind === "missing" ? null : summary.total);

  await page.goto("/queries");
  const row = page.locator(`a[href="/queries/${audit.id}"]`);
  await expect(row.getByTestId("cost-value")).toContainText(total);
  if (summary.kind === "partial") await expect(row).toContainText("unpriced");

  await row.click();
  await expect(page.getByRole("heading", { name: `Audit #${audit.id}` })).toBeVisible();
  await expect(page.getByTestId("cost-total")).toContainText(total);
  if (summary.kind === "partial") {
    await expect(page.getByTestId("cost-total")).toContainText("excludes unpriced usage");
  }
  for (const usage of providers) {
    const line = providerRow(page, usage);
    await expect(line).toHaveCount(1);
    await expect(line).toContainText(usage.cost_usd === null ? "unpriced" : formatUsd(usage.cost_usd));
  }
});
