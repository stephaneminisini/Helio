import { defineConfig, devices } from "@playwright/test";

/** Where the dev server serves the dashboard for the duration of the run. */
const BASE_URL = "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // The specs share one seeded database and the Setup spec writes to it, so
  // they run one at a time rather than racing each other for it.
  workers: 1,
  fullyParallel: false,
  // A smoke test that only passes on the second attempt is not a passing smoke
  // test: it is a broken build the retry hid.
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 30_000,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"]],
  use: {
    baseURL: BASE_URL,
    // Both are kept for failures only. A trace per passing test would fill the
    // artifact storage with runs nobody is ever going to open.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // The dev server proxies /api to the backend, so the browser talks to a
    // single origin and CORS never enters the picture. Point the proxy elsewhere
    // with HELIO_API_PROXY_TARGET if the API is not on localhost:8000.
    command: "npm run dev -- --port 5173 --strictPort",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
