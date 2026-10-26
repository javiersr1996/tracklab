import { defineConfig, devices } from "@playwright/test";

// Chromium only per task 18: no cross-browser matrix for the skeleton.
// BASE_URL points the suite at a deployment (task 23) instead of a local `next start`.
const BASE_URL = process.env.BASE_URL;
// Previews sit behind Vercel Authentication; this secret lets the suite through.
const BYPASS = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
// Locally another server may hold 3000: E2E_PORT moves the one this suite starts (`next start`
// reads PORT). CI leaves it unset and keeps 3000.
const PORT = process.env.E2E_PORT ?? "3000";
const LOCAL_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Locally the default (half the cores) starves the engine pages and fails unrelated tests; 4 passes.
  workers: process.env.CI ? undefined : 4,
  reporter: "html",
  use: {
    baseURL: BASE_URL ?? LOCAL_URL,
    trace: "on-first-retry",
    extraHTTPHeaders: BYPASS
      ? { "x-vercel-protection-bypass": BYPASS, "x-vercel-set-bypass-cookie": "true" }
      : undefined,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: BASE_URL
    ? undefined
    : {
    command: "npm run build && npm run start",
    url: LOCAL_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    // Builds with `window.__replay` exposed (task 21); a plain `next build` leaves it out.
    env: { NEXT_PUBLIC_EXPOSE_REPLAY: "1", PORT },
  },
});
