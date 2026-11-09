import { defineConfig, devices } from "@playwright/test";

import { ADMIN_URL, AUTH_STATE, MAIN_PASSWORD } from "./e2e/env";

const CI = Boolean(process.env.CI);

// Chromium by default; E2E_ALL_BROWSERS=1 adds Firefox and WebKit locally.
const browsers = process.env.E2E_ALL_BROWSERS
  ? ["Desktop Chrome", "Desktop Firefox", "Desktop Safari"]
  : ["Desktop Chrome"];

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  workers: CI ? 2 : undefined,
  reporter: CI
    ? [["list"], ["html", { open: "never" }], ["github"]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: ADMIN_URL,
    storageState: MAIN_PASSWORD ? AUTH_STATE : undefined,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Never the server's UTC, so SSR/hydration date mismatches surface in CI too.
    timezoneId: "Pacific/Auckland",
  },
  projects: browsers.map((device) => ({
    name: devices[device].defaultBrowserType,
    use: { ...devices[device] },
  })),
});
