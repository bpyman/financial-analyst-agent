import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // e2e/ is the Playwright browser check (`npm run test:e2e`), not a unit test.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
