import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";
import { display } from "../lib/learn/display";

// Lesson 11 end to end: every `data-fig` against the published clip it names or against
// `window.__learn`, the prose without digits, the per-player tables, and the page at a phone's
// width and a desktop's.
const expect = baseExpect.configure({ timeout: 20_000 });
const ROUTE = "/learn/facing";
// `window.__learn` exists in dev and test builds, not against a deployment.
const EXPOSED = !process.env.BASE_URL;
const SHOTS = process.env.LEARN_SHOTS; // a folder for full-page captures to look at, if set

const read = (...parts: string[]) => readFileSync(path.join(process.cwd(), ...parts), "utf-8");
const FENCE = JSON.parse(read("lib", "learn", "fence.json")) as { held_out: string[]; forbidden_keys: string[] };
const files = new Map<string, unknown>();
const dotted = (root: unknown, p: string) => p.split(".").reduce<unknown>((o, k) => (o !== null && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), root);
// "<file under public/data>:<dotted path>", read from disk.
function inFile(name: string): unknown {
  const [file, p] = name.split(":");
  if (!files.has(file)) files.set(file, JSON.parse(read("public", "data", ...file.split("/"))));
  return dotted(files.get(file), p);
}

type Computed = Record<string, any>;
const learn = (page: Page) => page.evaluate(() => window.__learn as Computed);

async function open(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(ROUTE);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Which way is a player facing?");
  if (EXPOSED) await expect.poll(() => page.evaluate(() => Boolean(window.__learn?.hook && window.__learn?.compass && window.__learn?.player))).toBe(true);
  return errors;
}

async function expectFigures(page: Page) {
  const figs = await page.locator("[data-fig]").evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig") ?? "", (e.textContent ?? "").trim()] as const));
  const computed = EXPOSED ? await learn(page) : null;
  const wrong: string[] = [];
  let fromFile = 0;
  let fromBrowser = 0;
  for (const [name, text] of figs) {
    if (name.startsWith("learn.")) {
      if (!computed) continue;
      fromBrowser++;
      const value = dotted(computed, name.slice(6));
      if (value === undefined || text !== display(String(value), name)) wrong.push(`${name}: page "${text}", browser ${String(value)}`);
    } else {
      fromFile++;
      const value = inFile(name);
      if (value === undefined || text !== display(String(value), name)) wrong.push(`${name}: page "${text}", file ${String(value)}`);
    }
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  return { fromFile, fromBrowser };
}

test.describe(ROUTE, () => {
  test("every data-fig is its file's or the browser's, before and after the reader acts", async ({ page }) => {
    const errors = await open(page);
    const first = await expectFigures(page);
    expect(first.fromFile).toBeGreaterThan(10);
    if (EXPOSED) expect(first.fromBrowser).toBeGreaterThan(100);

    const compass = page.locator('figure[data-figure="compass"]');
    const players = page.locator('figure[data-figure="players"]');
    const second = String(inFile("pose/hook_1996435.json:match_id"));
    await compass.getByRole("slider", { name: "Frame" }).fill("10");
    await compass.getByRole("radio", { name: second }).check();
    await players.getByRole("radio", { name: second }).check();
    await players.getByRole("slider", { name: "Player" }).fill("3");
    if (EXPOSED) {
      await expect.poll(async () => (await learn(page)).compass.match_id).toBe(Number(second));
      await expect.poll(async () => (await learn(page)).player.index).toBe(3);
      const l = await learn(page);
      // The compass's readout for the second clip is the lesson's figure for that clip.
      expect(l.compass.frames).toBe(l.hook[second].frames);
      expect(l.compass.circ_mean).toBe(l.hook[second].circ_mean);
      expect(l.compass.k).toBeLessThanOrEqual(10);
    }
    const after = await expectFigures(page);
    expect(after.fromFile).toBe(first.fromFile);
    console.log(`${ROUTE}: ${after.fromFile} figures from the files, ${after.fromBrowser} from the browser`);
    expect(errors).toEqual([]);
  });

  test("one table per clip, a row per qualifying player, as many as the plot draws", async ({ page }) => {
    await open(page);
    const tables = page.locator('figure[data-figure="players"] table[data-match]');
    await expect(tables).toHaveCount(2);
    for (const m of ["1925299", "1996435"]) {
      const rows = await page.locator(`figure[data-figure="players"] table[data-match="${m}"] tbody tr[data-row]`).count();
      expect(rows).toBeGreaterThanOrEqual(10);
      if (EXPOSED) expect(rows).toBe(((await learn(page)).players[m] as unknown[]).length);
      await page.locator('figure[data-figure="players"]').getByRole("radio", { name: m }).check();
      await expect(page.locator('figure[data-figure="players"] svg g[data-row]')).toHaveCount(rows);
      await expect(page.locator('figure[data-figure="players"] svg g[data-hook]')).toHaveCount(1);
    }
  });

  test("the prose has no digit once figures, formulas, citations, quotes, code and tables are out", async ({ page }) => {
    await open(page);
    const { digits, words } = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      const counted = main.cloneNode(true) as HTMLElement;
      counted.querySelectorAll("figure, pre, math").forEach((e) => e.remove());
      main.querySelectorAll("[data-fig], [data-series-n], math, cite, q, code, pre, table, figure").forEach((e) => e.remove());
      return {
        digits: (main.textContent ?? "").match(/.{0,30}\d+.{0,30}/g) ?? [],
        words: (counted.textContent ?? "").split(/\s+/).filter((w) => /[A-Za-z0-9]/.test(w)).length,
      };
    });
    console.log(`${ROUTE}: ${words} words`);
    expect(digits).toEqual([]);
  });

  test("no forbidden key outside a quote or a citation, no vetted phrase, no held-out id, and under 400,000 bytes", async ({ page }) => {
    const html = await (await page.request.get(ROUTE)).text();
    expect(html.length).toBeGreaterThan(10_000);
    expect(FENCE.held_out.filter((id) => html.includes(id))).toEqual([]);
    let bytes = 0;
    const sizes: Promise<void>[] = [];
    page.on("requestfinished", (r) => sizes.push(r.sizes().then((s) => void (bytes += s.responseBodySize + s.responseHeadersSize))));
    await page.goto(ROUTE);
    await page.waitForLoadState("networkidle");
    await Promise.all(sizes);
    console.log(`${ROUTE}: ${bytes} bytes transferred`);
    expect(bytes).toBeLessThan(400_000);
    const text = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      main.querySelectorAll("cite, q").forEach((e) => e.remove());
      return (main.textContent ?? "").toLowerCase();
    });
    expect(FENCE.forbidden_keys.filter((k) => text.includes(k))).toEqual([]);
    for (const phrase of ["time to impact", "second difference", "straight line", "constant speed", "detected"]) expect(text).not.toContain(phrase);
  });
});

for (const width of [390, 1440]) {
  test(`${ROUTE} at ${width} px: no sideways scroll, nothing under 16 px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await open(page);
    await page.waitForLoadState("networkidle");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .filter((el) => Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""))
        .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
        .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}`),
    );
    expect(small).toEqual([]);
    const scripts = await page.locator("main msub > :last-child, main msup > :last-child").evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
    expect(scripts.length).toBeGreaterThan(0);
    expect(Math.min(...scripts)).toBeGreaterThanOrEqual(16);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `facing-${width}.png`), fullPage: true });
  });
}
