import { defineConfig, devices } from "@playwright/test";

// Chromium only per task 18: no cross-browser matrix for the skeleton.
// BASE_URL points the suite at a deployment (task 23) instead of a local `next start`.
const BASE_URL = process.env.BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: BASE_URL
    ? undefined
    : {
    command: "npm run build && npm run start",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    // Builds with `window.__replay` exposed (task 21); a plain `next build` leaves it out.
    env: { NEXT_PUBLIC_EXPOSE_REPLAY: "1" },
  },
});
