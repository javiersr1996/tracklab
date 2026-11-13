import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { headerLinks, whole } from "./header";

// P15, task 121: the information architecture. /tracking is the hub of the pages that show the
// tracking itself (the occupancy map joined them in P23); each card opens its page.
test("the /tracking hub lists replay, runs, pose and occupancy as cards that open them", async ({ page }) => {
  await page.goto("/tracking");
  await expect(page.locator("h1")).toHaveText("Tracking");
  const cards = page.locator(".cards > li");
  await expect(cards).toHaveCount(4);
  expect(await cards.evaluateAll((els) => els.map((e) => e.getAttribute("data-section")))).toEqual([
    "/tracking/replay",
    "/tracking/runs",
    "/tracking/pose",
    "/tracking/occupancy",
  ]);
  await page.locator('[data-section="/tracking/runs"]').getByRole("link").click();
  await expect(page).toHaveURL(/\/tracking\/runs$/);
  await expect(page.locator("h1")).toHaveText("The run that moves nobody");
  await page.goto("/tracking");
  await page.locator('[data-section="/tracking/occupancy"]').getByRole("link").click();
  await expect(page).toHaveURL(/\/tracking\/occupancy$/);
  await expect(page.locator("h1")).toHaveText("Where football positions play");
});

// P23, Javier's "reorder it all": the home opens on what a visitor can watch and learn (the hero,
// then the lessons), then what to explore and what the site found, and how it is built at the end.
test("the home reads lessons, Explore, Findings, How it is built, and every card opens its page", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main h2")).toHaveText(["Start with a question", "Explore", "Findings", "How it is built"]);
  const order = (sel: string) => page.locator(sel).evaluateAll((els) => els.map((e) => e.getAttribute("data-section")));
  expect(await order(".home-explore .cards > li")).toEqual([
    "/tracking/replay",
    "/tracking/occupancy",
    "/warehouse/positions",
    "/euroleague",
    "/tracking/pose",
    "/tracking/runs",
    "/warehouse",
    "/warehouse/scouting",
  ]);
  expect(await order(".home-built .cards > li")).toEqual(["/engineering", "/engineering/quality"]);
  await expect(page.locator(".home-built figure[data-architecture]")).toHaveCount(1);
  await expect(page.locator(".home-built .figures")).toHaveCount(1);
  for (const href of await page.locator(".cards h3 a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!))) {
    expect((await page.request.get(href)).status(), href).toBe(200);
  }
  await page.locator('[data-section="/warehouse/positions"]').getByRole("link").click();
  await expect(page).toHaveURL(/\/warehouse\/positions$/);
});

// The lessons on the home are /learn's published ones, by their number (/learn groups them by
// level), each with its drawing; the counts in the prose are the lists' lengths on /learn and /sql,
// so a typed number fails here.
test("the home lists every published lesson with its drawing, and counts the lessons of /learn and /sql", async ({ page }) => {
  await page.goto("/learn");
  const published = (
    await page
      .locator(".lessons li[data-status=published]")
      .evaluateAll((els) =>
        els.map((e) => ({ slug: e.getAttribute("data-lesson")!, n: Number(e.querySelector("[data-series-n]")!.textContent) })),
      )
  )
    .sort((a, b) => a.n - b.n)
    .map((l) => l.slug);
  expect(published.length).toBeGreaterThan(0);
  await page.goto("/sql");
  const sql = await page.locator(".sql-lessons > li").count();
  expect(sql).toBeGreaterThan(0);

  await page.goto("/");
  const cards = page.locator(".questions > li");
  expect(await cards.evaluateAll((els) => els.map((e) => e.getAttribute("data-lesson")))).toEqual(published);
  for (const slug of published) {
    const card = page.locator(`.questions [data-lesson="${slug}"]`);
    await expect(card.locator(`svg[data-thumb="${slug}"]`)).toHaveCount(1);
    await expect(card.locator("h3 a")).toHaveAttribute("href", `/learn/${slug}`);
  }
  await expect(page.locator("[data-lesson-count]")).toHaveText(String(published.length));
  await expect(page.locator("[data-sql-count]")).toHaveText(String(sql));
  // The whole card opens its lesson: a click on the drawing, under the link's cover, goes there.
  const first = page.locator(`.questions [data-lesson="${published[0]}"] svg`);
  await first.scrollIntoViewIfNeeded();
  const box = (await first.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page).toHaveURL(new RegExp(`/learn/${published[0]}$`));
});

// The lessons are a rail on a phone that scrolls inside itself, never the page; a grid on a wide
// screen, every card inside the window.
for (const viewport of [
  { width: 390, height: 844 },
  { width: 1440, height: 900 },
]) {
  test(`at ${viewport.width} px the home's lessons fit, ${viewport.width < 1000 ? "a rail that scrolls inside itself" : "a grid"}, no sideways page scroll`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    const rail = page.locator(".questions");
    await rail.scrollIntoViewIfNeeded();
    const sideways = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(await sideways()).toBeLessThanOrEqual(0);
    const box = (await rail.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    const inner = await rail.evaluate((el) => el.scrollWidth - el.clientWidth);
    const cards = await page.locator(".questions > li").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON() as DOMRect));
    if (viewport.width < 1000) {
      expect(inner, "the rail scrolls sideways inside itself").toBeGreaterThan(0);
      expect(cards[0].x, "the first card starts at the gutter").toBeGreaterThanOrEqual(8);
      expect(cards[1].x, "the next one peeks in").toBeLessThan(viewport.width);
      // Scrolled to its end, the rail shows the last card whole and the page still does not scroll.
      await rail.evaluate((el) => el.scrollTo({ left: el.scrollWidth }));
      await expect.poll(async () => {
        const last = (await page.locator(".questions > li").last().boundingBox())!;
        return last.x + last.width;
      }).toBeLessThanOrEqual(viewport.width);
      expect(await sideways()).toBeLessThanOrEqual(0);
    } else {
      expect(inner, "no inner scroll on a wide screen").toBe(0);
      for (const c of cards) {
        expect(c.x).toBeGreaterThanOrEqual(0);
        expect(c.x + c.width).toBeLessThanOrEqual(viewport.width);
      }
    }
  });
}

// The header (Javier's option 1): the entries and About (P20), and under Tracking, Engineering,
// Warehouse (P17) or Learn (P21: the lessons and the SQL course, one idea, one entry) a second row
// with the group's pages, the one on show marked current.
const ENTRIES = ["Tracking", "Engineering", "Warehouse", "Learn", "EuroLeague", "About"];
const GROUPS = [
  { path: "/tracking/pose", group: "Tracking", pages: ["Replay", "Runs", "Pose", "Occupancy"], current: "Pose" },
  { path: "/tracking/occupancy", group: "Tracking", pages: ["Replay", "Runs", "Pose", "Occupancy"], current: "Occupancy" },
  { path: "/engineering/quality", group: "Engineering", pages: ["Platform", "Quality", "Bulletin", "History"], current: "Quality" },
  { path: "/engineering", group: "Engineering", pages: ["Platform", "Quality", "Bulletin", "History"], current: "Platform" },
  { path: "/engineering/history", group: "Engineering", pages: ["Platform", "Quality", "Bulletin", "History"], current: "History" },
  { path: "/warehouse", group: "Warehouse", pages: ["Console", "Scouting", "Positions"], current: "Console" },
  { path: "/warehouse/scouting", group: "Warehouse", pages: ["Console", "Scouting", "Positions"], current: "Scouting" },
  { path: "/warehouse/positions", group: "Warehouse", pages: ["Console", "Scouting", "Positions"], current: "Positions" },
  { path: "/learn", group: "Learn", pages: ["Lessons", "SQL course"], current: "Lessons" },
  { path: "/learn/gravity", group: "Learn", pages: ["Lessons", "SQL course"], current: "Lessons" },
  { path: "/sql", group: "Learn", pages: ["Lessons", "SQL course"], current: "SQL course" },
  { path: "/sql/joins", group: "Learn", pages: ["Lessons", "SQL course"], current: "SQL course" },
];

test("the header has the six entries, and a group's pages only under that group", async ({ page }) => {
  await page.goto("/euroleague");
  const nav = page.getByRole("navigation", { name: "Sections" });
  await expect(nav.getByRole("link")).toHaveText(ENTRIES);
  await expect(nav.locator("[aria-current]")).toHaveText(["EuroLeague"]);
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
  // A sub-link opens its page; Learn's opens the SQL course at its own address.
  await page.getByRole("navigation", { name: "Tracking" }).getByRole("link", { name: "Replay" }).click();
  await expect(page).toHaveURL(/\/tracking\/replay$/);
  await page.goto("/learn");
  await page.getByRole("navigation", { name: "Learn" }).getByRole("link", { name: "SQL course" }).click();
  await expect(page).toHaveURL(/\/sql$/);
  await expect(nav.locator("[aria-current]")).toHaveText(["Learn"]);
});

for (const width of [390, 1440]) {
  test(`at ${width} px the header's rows neither overlap nor overflow, the current links in view, text 16 px or more`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    // The wordmark and the six, then the group's row: four under Tracking (Occupancy, task 184b)
    // and under Engineering, three under Warehouse (Positions, task 184a), two under Learn.
    const LINKS: Record<string, number> = {
      "/": 7,
      "/tracking/runs": 11,
      "/tracking/occupancy": 11,
      "/engineering/bulletin": 11,
      "/engineering/history": 11,
      "/warehouse": 10,
      "/warehouse/scouting": 10,
      "/warehouse/positions": 10,
      "/learn/gravity": 9,
      "/sql/windows": 9,
      "/about": 7,
    };
    for (const path of Object.keys(LINKS)) {
      await page.goto(path);
      const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(sideways, `${path} wider than the window by`).toBeLessThanOrEqual(0);
      const links = await headerLinks(page);
      expect(links.length, path).toBe(LINKS[path]);
      for (const [i, a] of links.entries()) {
        const box = a.strip ?? { x: a.x, r: a.r };
        expect(box.x, `${path} link ${i}'s row starts inside the window`).toBeGreaterThanOrEqual(0);
        expect(box.r, `${path} link ${i}'s row ends inside the window`).toBeLessThanOrEqual(width);
        expect(a.size, `${path} link ${i} font size`).toBeGreaterThanOrEqual(16);
        // A link the row cuts is in a strip that scrolls; on a wide screen nothing is cut.
        if (!whole(a)) expect(a.strip?.scrolls && width < 640, `${path} ${a.text} cut by a row that does not scroll`).toBe(true);
        if (a.current) expect(whole(a), `${path} current ${a.text} in view`).toBe(true);
        for (const b of links.slice(i + 1)) {
          if (a.shownR <= a.shownX || b.shownR <= b.shownX) continue; // scrolled out of view
          const overlap = a.shownX < b.shownR && b.shownX < a.shownR && a.y < b.b && b.y < a.b;
          expect(overlap, `${path} header link ${i} overlaps another`).toBe(false);
        }
      }
      // The entries are one line, and on a phone the header is short: about 100 px, 140 with a
      // group's row (it was 143 and 196 px with the entries in two lines).
      const tops = new Set(links.slice(1, 7).map((l) => Math.round(l.y)));
      expect(tops.size, `${path}: the entries in one line`).toBe(1);
      if (width < 640) {
        const height = (await page.locator(".site-header").boundingBox())!.height;
        expect(height, `${path} header height`).toBeLessThanOrEqual(LINKS[path] > 7 ? 140 : 100);
      }
    }
  });
}

// On a phone the strip is still a list of links in the tab order: each one Tab reaches is brought
// into view inside the strip, so a keyboard reader sees where the focus is.
test("at 390 px Tab walks the header's strip and each focused link is in view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/engineering/history");
  const seen: string[] = [];
  for (let k = 0; k < 16 && seen.length < 10; k++) {
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => {
      const a = document.activeElement as HTMLElement | null;
      const ul = a?.closest(".site-nav ul");
      if (!a || !ul) return null;
      const r = a.getBoundingClientRect();
      const s = ul.getBoundingClientRect();
      return { text: a.textContent ?? "", inside: r.left >= s.left - 1 && r.right <= s.right + 1 };
    });
    if (!focus) continue;
    expect(focus.inside, `${focus.text} in view when focused`).toBe(true);
    seen.push(focus.text);
  }
  expect(seen).toEqual([...ENTRIES, "Platform", "Quality", "Bulletin", "History"]);
});

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

// P15, task 122: the footer is a short block on a phone (it was 622 px), the same text on every
// route, and the legal lines stay. The 560 px limit is there to catch a return to the old 622 px
// footer. The body font depends on the OS (--font-body resolves to Segoe UI on Windows and to
// another face on Linux), so the same footer measures about 476 px on Windows and 527.5 px on the
// GitHub Ubuntu runner; a tighter limit passes in one place and fails in the other.
// P20, task 171 adds the author line and a one-sentence disclaimer (four lines at 390 px): the
// footer measures 606.7 px on Windows (476.3 before), about 672 px by the same Ubuntu ratio
// (527.5 / 476.3). The limit moves by the same token to 700 px: the P15 layout that measured 622 px
// with the old text would measure about 750 px with the new one, and still fails here.
test("the footer is short at 390 px on every layout and keeps its notices", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  for (const route of ["/", "/tracking/runs", "/sql", "/learn", "/engineering", "/euroleague"]) {
    await page.goto(route);
    const footer = page.locator("footer.site-footer");
    const box = await footer.boundingBox();
    expect(box!.height, route).toBeLessThan(700);
    const labels = footer.locator(".site-footer-label", { hasText: /^code$/ });
    await expect(labels, route).toBeVisible();
    await expect(footer).toContainText("Not affiliated with SkillCorner.");
    await expect(footer).toContainText("Not affiliated with EuroLeague.");
    await expect(footer.getByRole("link", { name: "Code on GitHub, MIT license" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth), route).toBe(390);
  }
});
