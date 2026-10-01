import { defineConfig } from "@playwright/test";

// Smoke test of the real user journey against a running stack (API + web).
// Locally: `make api` + `make web`, then `make e2e`. Set PLAYWRIGHT_CHROMIUM to use a
// pre-installed browser instead of `npx playwright install chromium`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
});
