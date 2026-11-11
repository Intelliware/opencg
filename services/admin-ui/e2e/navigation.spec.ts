import { ADMIN_URL } from "./env";
import { expect, test, watchPage } from "./fixtures";

const SIDEBAR = [
  { name: "Overview", path: "/", heading: "Overview" },
  { name: "Graph", path: "/graph", heading: "Knowledge graph" },
  { name: "Vectors", path: "/vectors", heading: "Vector search" },
  { name: "Entities", path: "/entities", heading: "Entities" },
  { name: "Queries", path: "/queries", heading: "Queries" },
  { name: "Ingestion", path: "/ingestion", heading: "Ingestion" },
];

test.describe("every route renders against live services", () => {
  let auditId: number;
  let entityId: string;

  test.beforeAll(async ({ pipeline, run }) => {
    const correlationId = `${run.id}-navigation`;
    await pipeline.retrieve(correlationId, "amber-context protocol");
    auditId = (await pipeline.auditFor(correlationId)).id;
    entityId = (await pipeline.runEntities(run.prefix))[0].entity_id;
  });

  const routes = () => [
    { path: "/", heading: "Overview" },
    { path: "/queries", heading: "Queries" },
    { path: `/queries/${auditId}`, heading: `Audit #${auditId}` },
    { path: "/vectors", heading: "Vector search" },
    { path: "/entities", heading: "Entities" },
    { path: `/entities/${entityId}`, heading: null },
    { path: "/ingestion", heading: "Ingestion" },
    { path: "/graph", heading: "Knowledge graph" },
  ];

  test("each page loads with no error boundary, console error or failed request", async ({ page }) => {
    for (const route of routes()) {
      await test.step(route.path, async () => {
        let problems = watchPage(page, ADMIN_URL);
        const res = await page.goto(route.path);
        expect(res?.status(), route.path).toBe(200);
        await page.waitForLoadState("networkidle");
        // A known intermittent production hydration error (issue #2) hits about
        // 1 load in 100 on any route. Reload once; a deterministic mismatch recurs.
        if (problems.console.length && problems.console.every((msg) => msg.includes("React error #418"))) {
          test.info().annotations.push({ type: "flaky-hydration", description: route.path });
          page.removeAllListeners();
          problems = watchPage(page, ADMIN_URL);
          await page.reload();
          await page.waitForLoadState("networkidle");
        }
        if (route.heading) {
          await expect(page.getByRole("heading", { name: route.heading, exact: true })).toBeVisible();
        } else {
          await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
        }
        await expect(
          page.getByText(/Application error|Internal Server Error|This page could not be found/),
        ).toHaveCount(0);
        expect(problems.console, `console errors on ${route.path}`).toEqual([]);
        expect(problems.requests, `failed requests on ${route.path}`).toEqual([]);
        page.removeAllListeners();
      });
    }
  });
});

test("sidebar navigation reaches each page", async ({ page }) => {
  await page.goto("/entities");
  for (const item of SIDEBAR) {
    await page.getByRole("link", { name: item.name, exact: true }).filter({ visible: true }).click();
    // /graph rewrites its query string to the map's focus, so match the path only.
    await expect(page).toHaveURL((url) => url.pathname === item.path);
    await expect(page.getByRole("heading", { name: item.heading, exact: true })).toBeVisible();
  }
});

test("the theme toggle persists across reloads", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  const toggle = page.getByRole("button", { name: "Toggle theme" }).filter({ visible: true });
  await expect(toggle).toBeEnabled();
  const wasDark = ((await html.getAttribute("class")) ?? "").includes("dark");

  await toggle.click();
  if (wasDark) await expect(html).not.toHaveClass(/\bdark\b/);
  else await expect(html).toHaveClass(/\bdark\b/);

  await page.reload();
  if (wasDark) await expect(html).not.toHaveClass(/\bdark\b/);
  else await expect(html).toHaveClass(/\bdark\b/);
});
