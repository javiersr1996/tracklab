import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type Locator, type Page, test } from "@playwright/test";

// Task 184b: /tracking/occupancy against `occupancy.json`, which `tracklab publish occupancy` writes
// from the silver frames. Every expected figure below is computed here from the file, not read from
// the page's own helpers.

interface Group {
  group: string;
  player_frames: number;
  player_matches: number;
  matches: number;
  off_pitch: number;
  missing: number;
  share: number[];
}
interface File {
  sample_rate_hz: number;
  matches: string[];
  frames: number;
  grid: { cols: number; rows: number; length_m: number; width_m: number };
  share_scale: number;
  left_out: { goalkeeper: number };
  groups: Group[];
}
const FILE = JSON.parse(readFileSync(path.join(process.cwd(), "public", "data", "occupancy.json"), "utf-8")) as File;
const FENCE = JSON.parse(readFileSync(path.join(process.cwd(), "lib", "learn", "fence.json"), "utf-8")) as { held_out: string[] };
const PATH = "/tracking/occupancy";
const { cols, rows } = FILE.grid;
const slug = (g: string) => g.toLowerCase().replaceAll(" ", "-");
const n = (v: number) => v.toLocaleString("en-US");
const pct = (v: number) => `${(100 * v).toFixed(1)}%`;
const THIRDS = ["own third", "middle third", "attacking third"];
const LANES = ["right flank", "inside right", "centre", "inside left", "left flank"];

// The share of a group in each third (by column) and each lane (by row, from the right touchline).
function regions(g: Group) {
  const thirds = [0, 0, 0];
  const lanes = [0, 0, 0, 0, 0];
  g.share.forEach((s, i) => {
    thirds[Math.floor((3 * (i % cols)) / cols)] += s / FILE.share_scale;
    lanes[Math.floor((5 * Math.floor(i / cols)) / rows)] += s / FILE.share_scale;
  });
  const best = (v: number[]) => v.indexOf(Math.max(...v));
  return { thirds, lanes, third: THIRDS[best(thirds)], thirdShare: thirds[best(thirds)], lane: LANES[best(lanes)], laneShare: lanes[best(lanes)] };
}

async function transferred(page: Page) {
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  page.on("requestfinished", (r) => sizes.push(r.sizes().then((s) => void (bytes += s.responseBodySize + s.responseHeadersSize))));
  await page.goto(PATH);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  return bytes;
}

// Mean brightness of the left and right halves of what a locator shows, read off its screenshot.
async function halves(page: Page, el: Locator): Promise<{ left: number; right: number }> {
  const png = (await el.screenshot()).toString("base64");
  return page.evaluate(async (data) => {
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d")!;
    ctx.drawImage(img, 0, 0);
    const { data: px } = ctx.getImageData(0, 0, c.width, c.height);
    const sum = [0, 0];
    const count = [0, 0];
    for (let y = 0; y < c.height; y++)
      for (let x = 0; x < c.width; x++) {
        const i = 4 * (y * c.width + x);
        const side = x < c.width / 2 ? 0 : 1;
        sum[side] += px[i] + px[i + 1] + px[i + 2];
        count[side]++;
      }
    return { left: sum[0] / count[0], right: sum[1] / count[1] };
  }, png);
}

test("the file holds no held-out match, and the page prints its totals under the budget", async ({ page }) => {
  expect(FILE.matches.filter((m) => FENCE.held_out.includes(m))).toEqual([]);
  const bytes = await transferred(page);
  console.log(`${PATH}: ${bytes} bytes transferred`);
  expect(bytes).toBeLessThan(400_000);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Where football positions play");
  const outfield = FILE.groups[FILE.groups.length - 1];
  await expect(page.locator("[data-lede] [data-matches]")).toHaveText(String(FILE.matches.length));
  await expect(page.locator("[data-hz]")).toHaveText(String(FILE.sample_rate_hz));
  await expect(page.locator("[data-frames]")).toHaveText(n(FILE.frames));
  await expect(page.locator("[data-hours]")).toHaveText((FILE.frames / FILE.sample_rate_hz / 3600).toFixed(1));
  await expect(page.locator("[data-outfield]")).toHaveText(n(outfield.player_frames));
  await expect(page.locator("[data-goalkeepers]")).toHaveText(n(FILE.left_out.goalkeeper));
  await expect(page.locator("[data-off-pitch]")).toHaveText(pct(outfield.off_pitch / (outfield.player_frames + outfield.off_pitch + outfield.missing)));
  const html = await (await page.request.get(PATH)).text();
  expect(html).toMatch(/<meta name="description" content="[^"]+"/);
  const og = html.match(/<meta property="og:image" content="([^"]+)"/)?.[1];
  expect(og).toBeTruthy();
  const card = await page.request.get(new URL(og!).pathname + new URL(og!).search);
  expect(card.status()).toBe(200);
});

test("every map draws the file's cells over the floor, the largest share in the top step", async ({ page }) => {
  await page.goto(PATH);
  const top = Math.max(...FILE.groups.flatMap((g) => g.share));
  for (const g of FILE.groups) {
    const drawn = await page.locator(`#occ-${slug(g.group)} path`).evaluateAll((ps) =>
      ps.map((p) => ({ step: Number(p.getAttribute("data-step")), d: p.getAttribute("d") ?? "" })),
    );
    const cells = new Map<number, number>();
    for (const { step, d } of drawn)
      for (const m of d.matchAll(/M(\d+) (\d+)h(\d+)/g)) for (let k = 0; k < Number(m[3]); k++) cells.set(Number(m[2]) * cols + Number(m[1]) + k, step);
    const over = g.share.flatMap((s, i) => (s / FILE.share_scale >= 1e-4 ? [i] : []));
    expect([...cells.keys()].sort((a, b) => a - b), g.group).toEqual(over);
    const max = Math.max(...g.share);
    expect(cells.get(g.share.indexOf(max)), `${g.group}'s largest cell`).toBe(Math.min(8, Math.ceil((8 * max) / top)));
  }
  await expect(page.locator("[data-top]")).toHaveText(`${((100 * top) / FILE.share_scale).toFixed(2)}%`);
  await expect(page.locator('[data-edge="8"]')).toHaveText(`${((100 * top) / FILE.share_scale).toFixed(3)}%`);
});

test("a group button moves the large map, its title and its name to that group", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(PATH);
  const field = page.locator(".occ-field");
  let before = await field.screenshot();
  for (const [i, g] of FILE.groups.entries()) {
    const s = slug(g.group);
    await page.locator(`[data-group-button="${s}"]`).click();
    await expect(page.locator(`[data-group-button="${s}"]`)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".occ")).toHaveAttribute("data-group", s);
    await expect(page.locator(".occ-wide use")).toHaveAttribute("href", `#occ-${s}`);
    await expect(page.locator(".occ-title [data-field=player_frames]")).toHaveText(n(g.player_frames));
    await expect(page.locator(".occ-title [data-field=player_matches]")).toHaveText(n(g.player_matches));
    await expect(page.locator(".occ-title [data-field=matches]")).toHaveText(n(g.matches));
    const r = regions(g);
    await expect(page.getByRole("img", { name: `Heat map of the ${g.group.toLowerCase()} group` })).toHaveAttribute(
      "aria-label",
      new RegExp(`${r.third}, ${pct(r.thirdShare).replace(".", "\\.")} .*${r.lane}, ${pct(r.laneShare).replace(".", "\\.")}`),
    );
    if (i > 0) {
      const now = await field.screenshot();
      expect(now.equals(before), `${g.group}: the map changed`).toBe(false);
      before = now;
    }
  }
});

test("the maps face the attack: central defenders light the left half, centre forwards the right", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(PATH);
  const cd = await halves(page, page.locator(".occ-field"));
  expect(cd.left, "central defenders in their own half").toBeGreaterThan(cd.right * 1.5);
  await page.locator('[data-group-button="center-forward"]').click();
  await expect(page.locator(".occ-wide use")).toHaveAttribute("href", "#occ-center-forward");
  const cf = await halves(page, page.locator(".occ-field"));
  expect(cf.right, "centre forwards in the half they attack").toBeGreaterThan(cf.left * 1.5);
});

test("the tables print each group's busiest third and lane and every share, from the file", async ({ page }) => {
  await page.goto(PATH);
  // Row 0 of the grid is the right touchline: the lanes' columns run from the right flank.
  await expect(page.locator("[data-table=regions] thead th")).toHaveText(["position group", ...THIRDS, ...LANES]);
  for (const g of FILE.groups) {
    const s = slug(g.group);
    const r = regions(g);
    const row = page.locator(`[data-table=busiest] tr[data-group="${s}"]`);
    await expect(row.locator("[data-field=third]")).toHaveText(`${r.third}, ${pct(r.thirdShare)}`);
    await expect(row.locator("[data-field=lane]")).toHaveText(`${r.lane}, ${pct(r.laneShare)}`);
    await expect(row.locator("[data-field=player_frames]")).toHaveText(n(g.player_frames));
    await expect(row.locator("[data-field=player_matches]")).toHaveText(n(g.player_matches));
    await expect(row.locator("[data-field=off_pitch]")).toHaveText(n(g.off_pitch));
    await expect(page.locator(`[data-table=regions] tr[data-group="${s}"] [data-share]`)).toHaveText([...r.thirds, ...r.lanes].map(pct));
    await expect(page.locator(`.occ-multiples li[data-group="${s}"] [data-field=player_frames]`)).toHaveText(n(g.player_frames));
  }
});

for (const width of [390, 1440]) {
  test(`at ${width} px the pitch lies the right way, nothing scrolls sideways, text 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(PATH);
    await expect(page.locator(width < 768 ? ".occ-tall" : ".occ-wide")).toBeVisible();
    await expect(page.locator(width < 768 ? ".occ-wide" : ".occ-tall")).toBeHidden();
    const box = (await page.locator(".occ-field").boundingBox())!;
    if (width < 768) expect(box.height, "upright on a phone").toBeGreaterThan(box.width);
    else expect(box.width, "across on a wide screen").toBeGreaterThan(box.height);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    const sizes = await page.locator(".occ p, .occ span, .occ button, .occ figcaption, .occ-legend li, .occ-multiples p").evaluateAll((els) =>
      els.filter((e) => (e as HTMLElement).offsetParent !== null && e.textContent?.trim()).map((e) => parseFloat(getComputedStyle(e).fontSize)),
    );
    expect(sizes.length).toBeGreaterThan(10);
    for (const s of sizes) expect(s).toBeGreaterThanOrEqual(16);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}

test("the page and /warehouse/positions link each other, and the sitemap lists it", async ({ page }) => {
  await page.goto(PATH);
  await page.locator("main").getByRole("link", { name: "how football positions differ physically" }).click();
  await expect(page).toHaveURL(/\/warehouse\/positions$/);
  await page.locator("main").getByRole("link", { name: "where football positions play" }).click();
  await expect(page).toHaveURL(new RegExp(`${PATH}$`));
  const xml = await (await page.request.get("/sitemap.xml")).text();
  expect(xml).toContain(`${PATH}</loc>`);
});
