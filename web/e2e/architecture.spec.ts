import { expect, type Page, test } from "@playwright/test";
import { formatBytes } from "../lib/format";

// P20, task 173: the architecture drawn on the home page and at the head of /engineering. Its
// bytes are platform.json's; it reads left to right from 80rem and top to bottom on a phone, where
// it restacks instead of shrinking; its text stays at the site's floor; the flow stands still
// under prefers-reduced-motion.

interface Platform {
  layers: { layer: string; bytes: number }[];
  raw_sources: { source_id: string; bytes: number }[];
}

const ROUTES = ["/", "/engineering"];

async function platform(page: Page): Promise<Platform> {
  return (await (await page.request.get("/data/platform.json")).json()) as Platform;
}

for (const route of ROUTES) {
  test(`${route}: the architecture prints platform.json's bytes, in a captioned figure`, async ({ page }) => {
    const p = await platform(page);
    await page.goto(route);
    const fig = page.locator("figure[data-architecture]");
    await expect(fig).toHaveCount(1);
    const caption = fig.locator("figcaption");
    await expect(caption).toHaveAttribute("id", (await fig.getAttribute("aria-labelledby"))!);
    await expect(caption).toContainText("EuroLeague");
    await expect(fig.locator("[data-arch-stage]")).toHaveCount(p.layers.length);
    for (const l of p.layers) {
      await expect(fig.locator(`[data-layer-bytes="${l.layer}"]`)).toHaveText(formatBytes(l.bytes));
    }
    for (const s of p.raw_sources) {
      await expect(fig.locator(`[data-arch-source="${s.source_id}"]`)).toContainText(formatBytes(s.bytes));
    }
    // The order of the stages is the build's.
    expect(await fig.locator("[data-arch-stage]").evaluateAll((els) => els.map((e) => e.getAttribute("data-arch-stage")))).toEqual(
      p.layers.map((l) => l.layer),
    );
  });
}

test("every link of the architecture opens a page that answers, its #fragment an element of it", async ({ page }) => {
  await page.goto("/");
  const hrefs = await page.locator("figure[data-architecture] a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!));
  const local = [...new Set(hrefs.filter((h) => h.startsWith("/")))];
  expect(local.length).toBeGreaterThanOrEqual(8);
  for (const href of local) {
    const [path, id] = href.split("#");
    expect((await page.request.get(path)).status(), href).toBe(200);
    if (id) {
      await page.goto(path);
      await expect(page.locator(`[id="${id}"]`), href).toHaveCount(1);
    }
  }
});

const sizes = (page: Page) =>
  page.locator("figure[data-architecture]").evaluate((fig) => {
    const box = fig.getBoundingClientRect();
    const out: { text: string; size: number; left: number; right: number }[] = [];
    for (const el of fig.querySelectorAll("*")) {
      const own = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== "");
      if (!own) continue;
      const r = el.getBoundingClientRect();
      out.push({ text: (el.textContent ?? "").trim().slice(0, 30), size: parseFloat(getComputedStyle(el).fontSize), left: r.left - box.left, right: box.right - r.right });
    }
    return out;
  });

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1440, height: 900 },
]) {
  for (const route of ROUTES) {
    test(`${route} at ${viewport.width} px: the architecture's text is 16 px or more, inside the figure, no sideways scroll`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(route);
      await page.locator("figure[data-architecture]").scrollIntoViewIfNeeded();
      const texts = await sizes(page);
      expect(texts.length).toBeGreaterThan(20);
      for (const t of texts) {
        expect(t.size, t.text).toBeGreaterThanOrEqual(16);
        expect(t.left, `${t.text} starts inside the figure`).toBeGreaterThanOrEqual(0);
        expect(t.right, `${t.text} ends inside the figure`).toBeGreaterThanOrEqual(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    });
  }
}

const stageBoxes = (page: Page) =>
  page.locator("figure[data-architecture] [data-arch-stage]").evaluateAll((els) =>
    els.map((e) => {
      const r = e.getBoundingClientRect();
      return { x: Math.round(r.left), y: Math.round(r.top) };
    }),
  );

test("the layers read left to right at 1440 px and top to bottom at 390 px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const wide = await stageBoxes(page);
  expect(new Set(wide.map((b) => b.y)).size).toBe(1);
  for (let i = 1; i < wide.length; i++) expect(wide[i].x).toBeGreaterThan(wide[i - 1].x);
  await page.setViewportSize({ width: 390, height: 844 });
  const narrow = await stageBoxes(page);
  expect(new Set(narrow.map((b) => b.x)).size).toBe(1);
  for (let i = 1; i < narrow.length; i++) expect(narrow[i].y).toBeGreaterThan(narrow[i - 1].y);
});

const animations = (page: Page) =>
  page.locator("figure[data-architecture] [data-arch-stage]").evaluateAll((els) => els.map((e) => getComputedStyle(e, "::after").animationName));

test("the connectors flow, and stand still under prefers-reduced-motion", async ({ page }) => {
  await page.goto("/");
  expect(new Set(await animations(page))).not.toContain("none");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(new Set(await animations(page))).toEqual(new Set(["none"]));
});
