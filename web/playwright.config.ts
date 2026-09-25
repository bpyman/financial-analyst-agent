import { defineConfig, devices } from "@playwright/test";

/**
 * The browser check (ADR 0006 cutover criteria). With PLAYWRIGHT_BASE_URL unset
 * it starts the Python API on the recorded runtime and the built web app on
 * ports of their own; set it to run the same suite against a deployed window.
 * Build the app first (`npm run build`) for a local run.
 */
const API_PORT = 8100;
const WEB_PORT = 3100;
const target = process.env.PLAYWRIGHT_BASE_URL;
const ci = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: ci,
  retries: ci ? 1 : 0,
  // A hosted free-tier API has 0.1 CPU; go easy on it.
  workers: target ? 2 : undefined,
  timeout: 120_000,
  expect: { timeout: target ? 90_000 : 30_000 },
  reporter: ci ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: target ?? `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: target
    ? undefined
    : [
        {
          name: "API",
          command: "uv run serve-api",
          cwd: "..",
          // Explicit values beat a developer's .env: recorded runtime, no proxy token.
          env: { APP_MODE: "recorded", PUBLIC_DEMO: "false", API_PROXY_TOKEN: "", PORT: String(API_PORT) },
          url: `http://127.0.0.1:${API_PORT}/api/health`,
          reuseExistingServer: !ci,
          timeout: 120_000,
        },
        {
          name: "Web",
          command: `npm start -- --port ${WEB_PORT}`,
          env: { API_ORIGIN: `http://127.0.0.1:${API_PORT}`, API_PROXY_TOKEN: "" },
          url: `http://127.0.0.1:${WEB_PORT}`,
          reuseExistingServer: !ci,
          timeout: 120_000,
        },
      ],
});
