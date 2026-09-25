import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

/**
 * The portfolio capture (`npm run capture`, ADR 0006 cutover criteria). Same servers
 * as the browser check: the recorded API and the built app, or PLAYWRIGHT_BASE_URL.
 * Build the app first (`npm run build`) so no dev indicator shows in the images.
 */
export default defineConfig({
  ...base,
  testDir: "./scripts",
  testMatch: "capture-portfolio.ts",
  outputDir: "./test-results/capture",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  reporter: "list",
  use: { ...base.use, trace: "off", screenshot: "off", video: "off" },
  projects: [{ name: "capture" }],
});
