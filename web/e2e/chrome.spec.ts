import { expect, test } from "@playwright/test";

// P19, tasks 151 and 152: the 404, the skip link and the text size of the /engineering figures.

test("an address that does not exist gets the site's 404 with the header and footer", async ({ page }) => {
  const res = await page.goto("/no-such-page");
  expect(res?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("This page does not exist");
  await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible();
  await expect(page.locator(".site-footer")).toBeVisible();
  await expect(page.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
});

for (const width of [390, 1440]) {
  test(`skip link: hidden until focused, first Tab stop, jumps to main at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/engineering/quality");
    const link = page.getByRole("link", { name: "Skip to content" });
    const hidden = await link.boundingBox();
    expect(hidden!.y + hidden!.height).toBeLessThanOrEqual(0);
    await page.keyboard.press("Tab");
    await expect(link).toBeFocused();
    const shown = await link.boundingBox();
    expect(shown!.y).toBeGreaterThanOrEqual(0);
    expect(shown!.x + shown!.width).toBeLessThanOrEqual(width);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main$/);
    await expect(page.locator("main#main")).toHaveCount(1);
  });
}

// An svg's text is in user units: its shown size is the computed font size times width / viewBox.
const shownSizes = () =>
  Array.from(document.querySelectorAll("svg text")).map((t) => {
    const svg = (t as SVGTextElement).ownerSVGElement!;
    return parseFloat(getComputedStyle(t).fontSize) * (svg.getBoundingClientRect().width / svg.viewBox.baseVal.width);
  });

for (const width of [390, 1440]) {
  for (const path of ["/engineering", "/engineering/history"]) {
    test(`figure text on ${path} is at the site's floor at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      // The floor is what a tick of another figure measures (--step-0), not a number typed here.
      const floor = await page.evaluate(() => parseFloat(getComputedStyle(document.body).fontSize));
      const sizes = await page.evaluate(shownSizes);
      expect(sizes.length).toBeGreaterThan(50);
      expect(Math.min(...sizes)).toBeGreaterThanOrEqual(floor - 0.01); // svg widths round to a sub-pixel
    });
  }
}
