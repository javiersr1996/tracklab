import { expect, type Page, test } from "@playwright/test";

const WIDTHS = [390, 1440];

// Bytes transferred by a page load, the way the other specs count them.
async function transferred(page: Page, path: string) {
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  page.on("requestfinished", (r) =>
    sizes.push(
      r.sizes().then((s) => {
        bytes += s.responseBodySize + s.responseHeadersSize;
      }),
    ),
  );
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  return bytes;
}

test("the index links the published lesson, lists the next ones without a link and none from after", async ({ page }) => {
  const bytes = await transferred(page, "/learn");
  console.log(`/learn: ${bytes} bytes transferred`);
  expect(bytes).toBeLessThan(400_000);

  const published = page.locator('[data-status="published"]');
  await expect(published).toHaveCount(1);
  await expect(published.getByRole("link", { name: "Does the ball obey gravity?" })).toHaveAttribute("href", "/learn/gravity");

  const pending = page.locator('[data-status="in-preparation"]');
  expect(await pending.count()).toBeGreaterThan(0);
  await expect(pending.locator("a")).toHaveCount(0);
  await expect(pending.first()).toContainText("In preparation");

  // Lessons 6 and 7 come after the fence: the series stops at 5.
  const numbers = await page.locator("[data-series-n]").evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-series-n"))));
  expect(Math.max(...numbers)).toBeLessThanOrEqual(5);
  expect(numbers).toEqual([...numbers].sort((a, b) => a - b));
});

test("the lesson link opens a page, not a 404", async ({ page }) => {
  await page.goto("/learn");
  await page.getByRole("link", { name: "Does the ball obey gravity?" }).click();
  await expect(page).toHaveURL(/\/learn\/gravity$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Does the ball obey gravity?");
  await expect(page.locator("[data-series-n]")).toHaveText("1");
});

test("the header marks Learn current on the index and on a lesson, and only there", async ({ page }) => {
  const learn = page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: "Learn" });
  for (const path of ["/learn", "/learn/gravity"]) {
    await page.goto(path);
    await expect(learn).toHaveAttribute("aria-current", "page");
    await expect(page.locator('nav[aria-label="Sections"] [aria-current]')).toHaveCount(1);
  }
  await page.goto("/quality");
  await expect(learn).not.toHaveAttribute("aria-current", "page");
});

test("the home page links /learn", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('a[href="/learn"]').first()).toBeVisible();
});

for (const width of WIDTHS) {
  for (const path of ["/", "/learn", "/learn/gravity"]) {
    test(`${path} at ${width} px: no sideways scroll, no overlaps, nothing under 16 px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(sideways, "page wider than the window by").toBeLessThanOrEqual(0);

      // The header too: seven links wrap on a phone and must not collide.
      const links = await page.locator(".site-nav a").evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return { x: r.left, y: r.top, r: r.right, b: r.bottom };
        }),
      );
      for (let i = 0; i < links.length; i++) {
        for (let j = i + 1; j < links.length; j++) {
          const a = links[i];
          const b = links[j];
          const overlap = a.x < b.r && b.x < a.r && a.y < b.b && b.y < a.b;
          expect(overlap, `header links ${i} and ${j} overlap`).toBe(false);
        }
      }

      // Text of every element, MathML included, is 16 px or more.
      const small = await page.evaluate(() =>
        Array.from(document.querySelectorAll("main *"))
          .filter((el) =>
            Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""),
          )
          .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
          .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}`),
      );
      expect(small, "text under 16 px").toEqual([]);

      if (path === "/learn/gravity") {
        // The check has to see the scripts, or it protects nothing: every subscript and superscript.
        const scripts = await page
          .locator("main msub > :last-child, main msup > :last-child")
          .evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
        expect(scripts.length).toBeGreaterThan(0);
        expect(Math.min(...scripts)).toBeGreaterThanOrEqual(16);
      }
    });
  }
}
