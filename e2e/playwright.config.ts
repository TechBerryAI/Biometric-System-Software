import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://localhost:5173";

/**
 * Browser E2E against a running stack (`make start` or `make start-vm`).
 * Does not start servers by default — set E2E_BASE_URL if the frontend is not on :5173.
 * Optional: set E2E_START_WEBSERVER=1 to let Playwright boot `npm --prefix frontend run dev`.
 */
export default defineConfig({
  testDir: "./scenarios",
  outputDir: "./test-results",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  ...(process.env.E2E_START_WEBSERVER === "1"
    ? {
        webServer: {
          command: "npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173",
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          cwd: "..",
        },
      }
    : {}),
});
