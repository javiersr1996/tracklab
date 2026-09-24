import { test, expect } from "@playwright/test";

test("home page loads with the site title", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Track Lab");
});
