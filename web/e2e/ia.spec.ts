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

// The header (Javier's option 1): six entries, and under Tracking or Engineering a second row
// with the group's pages, the one on show marked current.
const SIX = ["Tracking", "Engineering", "Warehouse", "Learn", "SQL", "EuroLeague"];
const GROUPS = [
  { path: "/tracking/pose", group: "Tracking", pages: ["Replay", "Runs", "Pose"], current: "Pose" },
  { path: "/engineering/quality", group: "Engineering", pages: ["Platform", "Quality", "Bulletin"], current: "Quality" },
  { path: "/engineering", group: "Engineering", pages: ["Platform", "Quality", "Bulletin"], current: "Platform" },
];

test("the header has the six entries, and a group's pages only under that group", async ({ page }) => {
  await page.goto("/warehouse");
  const nav = page.getByRole("navigation", { name: "Sections" });
  await expect(nav.getByRole("link")).toHaveText(SIX);
  await expect(nav.locator("[aria-current]")).toHaveText(["Warehouse"]);
  await expect(page.locator(".site-subnav")).toHaveCount(0);

  for (const g of GROUPS) {
    await page.goto(g.path);
    await expect(nav.locator("[aria-current]")).toHaveText([g.group]);
    const sub = page.getByRole("navigation", { name: g.group });
    await expect(sub.getByRole("link")).toHaveText(g.pages);
    await expect(sub.locator("[aria-current]")).toHaveText([g.current]);
  }
  // The hub itself: its group's row, no page of it current.
  await page.goto("/tracking");
  await expect(page.getByRole("navigation", { name: "Tracking" }).locator("[aria-current]")).toHaveCount(0);
  // A sub-link opens its page.
  await page.getByRole("navigation", { name: "Tracking" }).getByRole("link", { name: "Replay" }).click();
  await expect(page).toHaveURL(/\/tracking\/replay$/);
});

for (const width of [390, 1440]) {
  test(`at ${width} px the header's two rows neither overlap nor overflow, text 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/tracking/runs", "/engineering/bulletin"]) {
      await page.goto(path);
      const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(sideways, `${path} wider than the window by`).toBeLessThanOrEqual(0);
      const links = await page.locator(".site-header a").evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return { x: r.left, y: r.top, r: r.right, b: r.bottom, size: parseFloat(getComputedStyle(e).fontSize) };
        }),
      );
      expect(links.length, path).toBe(path === "/" ? 7 : 10); // the wordmark, six, and three
      for (const [i, a] of links.entries()) {
        expect(a.x, `${path} link ${i} starts inside the window`).toBeGreaterThanOrEqual(0);
        expect(a.r, `${path} link ${i} ends inside the window`).toBeLessThanOrEqual(width);
        expect(a.size, `${path} link ${i} font size`).toBeGreaterThanOrEqual(16);
        for (const b of links.slice(i + 1)) {
          expect(a.x < b.r && b.x < a.r && a.y < b.b && b.y < a.b, `${path} header link ${i} overlaps another`).toBe(false);
        }
      }
    }
  });
}
