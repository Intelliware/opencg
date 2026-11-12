#!/usr/bin/env node
// Hydration stress check for the admin UI (upgrade-admin-ui-next-16, design D3).
//
// Issue #2 (React error #418) only showed up in a production build with several
// browsers competing for CPU. This script reproduces that load: BROWSERS
// concurrent Chromium processes each load every admin route CYCLES times, and
// it counts
//   - React hydration errors (#418),
//   - other console errors and page errors,
//   - pages whose <main> heading never hydrated (no React fiber on it),
//   - sidebar navigations that do not commit within 5 s,
//   - /queries row navigations that do not commit within 5 s (once per cycle).
// It prints a JSON summary and exits non-zero if any counter is above zero.
//
// Needs a seeded stack (run after `make smoke` or `make e2e`).
//
// Env: BASE_URL (default http://127.0.0.1:${OPENCG__ADMIN_UI__HOST_PORT:-3000}),
//      BROWSERS (7), CYCLES (30), SUMMARY_FILE (optional path for the JSON).
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium, devices } = require("@playwright/test");

const REPO_ROOT = path.resolve(__dirname, "../../..");

function dotenv() {
  try {
    const values = {};
    for (const line of fs.readFileSync(path.join(REPO_ROOT, ".env"), "utf8").split("\n")) {
      const match = /^([A-Z0-9_]+)=(.*)$/.exec(line);
      if (match) values[match[1]] = match[2];
    }
    return values;
  } catch {
    return {};
  }
}

const fileEnv = dotenv();
const setting = (key, fallback) => process.env[key] || fileEnv[key] || fallback;

const BASE_URL = (
  process.env.BASE_URL || `http://127.0.0.1:${setting("OPENCG__ADMIN_UI__HOST_PORT", "3000")}`
).replace(/\/$/, "");
const BROWSERS = Number(process.env.BROWSERS || 7);
const CYCLES = Number(process.env.CYCLES || 30);
const NAV_TIMEOUT_MS = 5000;

const SIDEBAR = ["/", "/graph", "/vectors", "/entities", "/queries", "/ingestion"];
const SIDEBAR_NAMES = {
  "/": "Overview",
  "/graph": "Graph",
  "/vectors": "Vectors",
  "/entities": "Entities",
  "/queries": "Queries",
  "/ingestion": "Ingestion",
};

async function firstDetailHref(page, listPath, prefix) {
  await page.goto(BASE_URL + listPath);
  await page.waitForLoadState("networkidle");
  const link = page.locator(`main a[href^='${prefix}']`).first();
  if ((await link.count()) === 0) return null;
  return link.getAttribute("href");
}

async function waitForPath(page, predicate) {
  const deadline = Date.now() + NAV_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (predicate(new URL(page.url()).pathname)) return true;
    await page.waitForTimeout(100);
  }
  return false;
}

async function main() {
  const counts = {
    loads: 0,
    hydration_418: 0,
    other_console_errors: 0,
    unhydrated_pages: 0,
    stuck_sidebar_navigations: 0,
    stuck_row_navigations: 0,
  };
  const samples = [];
  const note = (kind, route, detail) => {
    if (samples.length < 20) samples.push({ kind, route, detail: String(detail).slice(0, 200) });
  };

  // Detail ids from the seeded data.
  const seedBrowser = await chromium.launch();
  const seedPage = await seedBrowser.newPage();
  const queryHref = await firstDetailHref(seedPage, "/queries", "/queries/");
  const entityHref = await firstDetailHref(seedPage, "/entities", "/entities/");
  await seedBrowser.close();
  if (!queryHref || !entityHref) {
    console.error(
      `hydration-stress: no seed data (queries=${queryHref}, entities=${entityHref}). ` +
        "Run `make smoke` or `make e2e` first.",
    );
    process.exit(2);
  }
  const routes = ["/", "/queries", queryHref, "/vectors", "/entities", entityHref, "/ingestion", "/graph"];

  const started = Date.now();
  await Promise.all(
    Array.from({ length: BROWSERS }, async (_, worker) => {
      const browser = await chromium.launch();
      const page = await browser.newPage({ ...devices["Desktop Chrome"], timezoneId: "Pacific/Auckland" });
      let route = "";
      page.on("pageerror", (err) => {
        const text = String(err);
        if (text.includes("#418")) {
          counts.hydration_418++;
          note("418", route, text);
        } else {
          counts.other_console_errors++;
          note("pageerror", route, text);
        }
      });
      page.on("console", (msg) => {
        if (msg.type() !== "error") return;
        const text = msg.text();
        if (text.includes("#418")) return; // also raised as a pageerror; count once
        counts.other_console_errors++;
        note("console", route, text);
      });
      try {
        for (let cycle = 0; cycle < CYCLES; cycle++) {
          for (const r of routes) {
            route = r;
            counts.loads++;
            await page.goto(BASE_URL + r);
            await page.waitForLoadState("networkidle");
            const hydrated = await page.evaluate(() => {
              const heading = document.querySelector("main h1, main h2");
              return !!heading && Object.keys(heading).some((k) => k.startsWith("__reactFiber$"));
            });
            if (!hydrated) {
              counts.unhydrated_pages++;
              note("unhydrated", r, "main heading has no React fiber");
            }
            const current = new URL(page.url()).pathname;
            const target = SIDEBAR[(SIDEBAR.indexOf(current) + 1 + worker) % SIDEBAR.length];
            const dest = target === current ? "/queries" : target;
            await page
              .locator("aside")
              .getByRole("link", { name: SIDEBAR_NAMES[dest], exact: true })
              .first()
              .click();
            if (!(await waitForPath(page, (p) => p === dest))) {
              counts.stuck_sidebar_navigations++;
              note("stuck_sidebar", r, `to ${dest}`);
            }
          }
          // One row click per cycle: the transition that hung with app/loading.tsx.
          route = "/queries (row)";
          await page.goto(BASE_URL + "/queries");
          await page.waitForLoadState("networkidle");
          const row = page.locator("main a[href^='/queries/']").first();
          const href = await row.getAttribute("href");
          await row.click();
          if (!(await waitForPath(page, (p) => p === href))) {
            counts.stuck_row_navigations++;
            note("stuck_row", "/queries", `to ${href}`);
          }
        }
      } finally {
        await browser.close();
      }
    }),
  );

  const failures = Object.entries(counts)
    .filter(([key, value]) => key !== "loads" && value > 0)
    .map(([key]) => key);
  const summary = {
    base_url: BASE_URL,
    browsers: BROWSERS,
    cycles: CYCLES,
    routes,
    seconds: Math.round((Date.now() - started) / 1000),
    ...counts,
    passed: failures.length === 0,
    samples,
  };
  const json = JSON.stringify(summary, null, 2);
  console.log(json);
  if (process.env.SUMMARY_FILE) fs.writeFileSync(process.env.SUMMARY_FILE, json + "\n");
  process.exit(failures.length === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
