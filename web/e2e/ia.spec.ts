import { expect, test } from "@playwright/test";

// P15, task 121: the information architecture. /tracking is the hub of the three pages that
// show the tracking itself; each card opens its page.
test("the /tracking hub lists replay, runs and pose as cards that open them", async ({ page }) => {
  await page.goto("/tracking");
  await expect(page.locator("h1")).toHaveText("Tracking");
  const cards = page.locator(".cards > li");
  await expect(cards).toHaveCount(3);
  expect(await cards.evaluateAll((els) => els.map((e) => e.getAttribute("data-section")))).toEqual([
    "/tracking/replay",
    "/tracking/runs",
    "/tracking/pose",
  ]);
  await page.locator('[data-section="/tracking/runs"]').getByRole("link").click();
  await expect(page).toHaveURL(/\/tracking\/runs$/);
  await expect(page.locator("h1")).toHaveText("The run that moves nobody");
});
