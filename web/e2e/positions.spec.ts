import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type Page, test } from "@playwright/test";

// Task 184a: /warehouse/positions, the football physical aggregates of the scouting pools by
// position group. Its pools are compared with scouting.json (counted in Python), and its medians
// with what the console returns when the query the page prints is pasted into it: another engine
// run, in the browser, on the same Parquet file.

interface Scouting {
  tables: { table: string; floor: string; metrics: { id: string; label: string }[]; pools: { group: string; players: number; n: number[] }[] }[];
}
const SCOUTING = JSON.parse(readFileSync(path.join(process.cwd(), "public", "data", "scouting.json"), "utf-8")) as Scouting;
const PHYSICAL = SCOUTING.tables.find((t) => t.table === "fb_physical")!;
const PATH = "/warehouse/positions";
const num = (s: string | null) => Number((s ?? "").replaceAll(",", ""));

async function transferred(page: Page) {
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  page.on("requestfinished", (r) => sizes.push(r.sizes().then((s) => void (bytes += s.responseBodySize + s.responseHeadersSize))));
  await page.goto(PATH);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  return bytes;
}

test("prints scouting.json's pools and floor, under the budget, with a description and a card", async ({ page }) => {
  const bytes = await transferred(page);
  console.log(`${PATH}: ${bytes} bytes transferred`);
  expect(bytes).toBeLessThan(400_000);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("How football positions differ physically");
  await expect(page.locator("[data-floor]")).toHaveText(PHYSICAL.floor);
  for (const p of PHYSICAL.pools) {
    await expect(page.locator(`.pos-table tr[data-group="${p.group}"] [data-n]`)).toHaveText(String(p.players));
    await expect(page.locator(`.pos-card[data-group="${p.group}"] [data-n]`)).toHaveText(String(p.n[0]));
  }
  const html = await (await page.request.get(PATH)).text();
  expect(html).toMatch(/<meta name="description" content="[^"]+"/);
  const og = html.match(/<meta property="og:image" content="([^"]+)"/)?.[1];
  expect(og).toBeTruthy();
  const card = await page.request.get(new URL(og!).pathname + new URL(og!).search);
  expect(card.status()).toBe(200);
  expect(card.headers()["content-type"]).toBe("image/png");
});

test("the switcher moves the pitch, the ranking and the query to the metric picked", async ({ page }) => {
  await page.goto(PATH);
  const buttons = page.locator("[data-metric-button]");
  const ids = await buttons.evaluateAll((els) => els.map((e) => e.getAttribute("data-metric-button")!));
  expect(ids.length).toBeGreaterThanOrEqual(3);
  for (const id of ids) {
    const metric = PHYSICAL.metrics.find((m) => m.id === id)!;
    const k = PHYSICAL.metrics.indexOf(metric);
    await page.locator(`[data-metric-button="${id}"]`).click();
    await expect(page.locator(`[data-metric-button="${id}"]`)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".pos")).toHaveAttribute("data-metric", id);
    await expect(page.locator(".pos-title")).toContainText(metric.label);
    await expect(page.locator("pre[data-sql]")).toContainText(`quantile_cont(${id}, 0.5)`);
    for (const p of PHYSICAL.pools) {
      // The card, the ranking and the table say the same median; n is the metric's pool.
      const fromTable = await page.locator(`.pos-table tr[data-group="${p.group}"] td[data-metric="${id}"] [data-median]`).textContent();
      await expect(page.locator(`.pos-card[data-group="${p.group}"] [data-median]`)).toHaveText(fromTable!);
      await expect(page.locator(`.pos-ranked li[data-group="${p.group}"] [data-median]`)).toHaveText(fromTable!);
      await expect(page.locator(`.pos-ranked li[data-group="${p.group}"] [data-n]`)).toHaveText(String(p.n[k]));
      await expect(page.locator(`.pos-ranked li[data-group="${p.group}"] .pos-dot`)).toHaveCount(p.n[k]);
    }
    const medians = await page.locator(".pos-ranked li [data-median]").allTextContents();
    expect(medians.map(num), `${id} ranked`).toEqual([...medians.map(num)].sort((a, b) => b - a));
  }
});

test("the printed query, run in the console, returns the page's n and quartiles", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto(PATH);
  const sql = (await page.locator("pre[data-sql]").textContent())!;
  const shown = await page.locator(".pos-ranked li").evaluateAll((lis) =>
    lis.map((li) => ["data-group", "[data-n]", "[data-q1]", "[data-median]", "[data-q3]"].map((s, i) => (i === 0 ? li.getAttribute(s) : li.querySelector(s)?.textContent ?? ""))),
  );
  await page.goto("/warehouse");
  await page.getByLabel("SQL").fill(sql);
  const figure = page.locator("figure.warehouse");
  const before = Number(await figure.getAttribute("data-run"));
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure).toHaveAttribute("data-run", String(before + 1));
  await expect(figure).toHaveAttribute("data-query", "done", { timeout: 180_000 });
  expect(await page.locator("figure.warehouse > .table-scroll thead th").allTextContents()).toEqual(["position_group", "n", "q1", "median", "q3"]);
  const rows = await page
    .locator("figure.warehouse > .table-scroll tbody tr")
    .evaluateAll((trs) => trs.map((tr) => Array.from(tr.querySelectorAll("td"), (td) => td.textContent ?? "")));
  expect(rows.map((r) => [r[0], num(r[1]), num(r[2]), num(r[3]), num(r[4])])).toEqual(shown.map((r) => [r[0], num(r[1]), num(r[2]), num(r[3]), num(r[4])]));
});

for (const width of [390, 1440]) {
  test(`at ${width} px the cards sit inside the pitch apart from each other, text 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(PATH);
    for (const id of await page.locator("[data-metric-button]").evaluateAll((els) => els.map((e) => e.getAttribute("data-metric-button")!))) {
      await page.locator(`[data-metric-button="${id}"]`).click();
      const field = (await page.locator(".pos-field").boundingBox())!;
      const cards = await page.locator(".pos-card").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON() as DOMRect));
      expect(cards).toHaveLength(PHYSICAL.pools.length);
      for (const [i, c] of cards.entries()) {
        expect(c.left, `${id} card ${i} left`).toBeGreaterThanOrEqual(field.x);
        expect(c.right, `${id} card ${i} right`).toBeLessThanOrEqual(field.x + field.width);
        expect(c.top, `${id} card ${i} top`).toBeGreaterThanOrEqual(field.y);
        expect(c.bottom, `${id} card ${i} bottom`).toBeLessThanOrEqual(field.y + field.height);
        for (const d of cards.slice(i + 1)) {
          const overlap = c.left < d.right && d.left < c.right && c.top < d.bottom && d.top < c.bottom;
          expect(overlap, `${id}: two cards overlap`).toBe(false);
        }
      }
    }
    const sizes = await page.locator(".pos p, .pos span, .pos button, .pos output, .pos figcaption, .pos code").evaluateAll((els) =>
      els.filter((e) => (e as HTMLElement).offsetParent !== null && e.textContent?.trim()).map((e) => parseFloat(getComputedStyle(e).fontSize)),
    );
    for (const s of sizes) expect(s).toBeGreaterThanOrEqual(16);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}

test("/warehouse links the page, and the sitemap lists it", async ({ page }) => {
  await page.goto("/warehouse");
  await page.locator("main").getByRole("link", { name: "How football positions differ physically" }).click();
  await expect(page).toHaveURL(new RegExp(`${PATH}$`));
  const xml = await (await page.request.get("/sitemap.xml")).text();
  expect(xml).toContain(`${PATH}</loc>`);
});
