import { readFileSync } from "node:fs";
import { join } from "node:path";
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

// The old routes answer with a permanent redirect to the new ones, the query carried over. The
// list is typed here, not read from next.config.ts, so a redirect dropped there fails here.
const MOVED: [string, string][] = [
  ["/replay", "/tracking/replay"],
  ["/runs", "/tracking/runs"],
  ["/pose", "/tracking/pose"],
  ["/platform", "/engineering"],
  ["/quality", "/engineering/quality"],
  ["/bulletin", "/engineering/bulletin"],
];

test("each old route redirects permanently to its new home, and the new one answers 200", async ({ page }) => {
  for (const [from, to] of MOVED) {
    const res = await page.request.get(from, { maxRedirects: 0 });
    expect([301, 308], `${from} status`).toContain(res.status());
    expect(new URL(res.headers()["location"], "http://x").pathname, `${from} location`).toBe(to);
    expect((await page.request.get(to, { maxRedirects: 0 })).status(), `${to} status`).toBe(200);
  }
  const res = await page.request.get("/replay?p=bb_possessions_possession-114243-3-79.json", { maxRedirects: 0 });
  expect(res.headers()["location"]).toMatch(/\/tracking\/replay\?p=bb_possessions_possession-114243-3-79\.json$/);
  // A browser lands on the page itself.
  await page.goto("/platform");
  await expect(page).toHaveURL(/\/engineering$/);
  await expect(page.getByRole("navigation", { name: "Sections" }).locator("[aria-current]")).toHaveText(["Engineering"]);
});

// The bulletin under /engineering renders its Markdown (it printed `## Detection` as written): a
// heading per `## ` line of docs/bulletin.md, code spans as code, the dataset card as a link.
test("the bulletin's sections are headings, its code is code and its source a link", async ({ page }) => {
  const md = readFileSync(join(process.cwd(), "..", "docs", "bulletin.md"), "utf-8");
  const headings = [...md.matchAll(/^## (.+)$/gm)].map((m) => m[1]);
  expect(headings.length).toBeGreaterThan(0);
  await page.goto("/engineering/bulletin");
  await expect(page.locator("main h2")).toHaveText(headings);
  await expect(page.locator("main")).not.toContainText("## ");
  await expect(page.locator("main")).not.toContainText("`");
  await expect(page.locator(".bulletin code").first()).toBeVisible();
  await expect(page.locator(".bulletin blockquote")).toHaveCount((md.match(/^> /gm) ?? []).length);
  await expect(page.locator(".bulletin a", { hasText: "SkillCorner/opendata-bodypose" })).toHaveAttribute(
    "href",
    "https://huggingface.co/datasets/SkillCorner/opendata-bodypose",
  );
});
