import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";
import { display } from "../lib/learn/display";

// Lesson 10 in the browser. The figures are read back from possession.json and `window.__learn`, never
// typed here.
const expect = baseExpect.configure({ timeout: 20_000 });

const ROUTE = "/learn/possession";
const EXPOSED = !process.env.BASE_URL;
const SHOTS = process.env.LEARN_SHOTS; // a folder for full-page captures to look at, if set

const read = (...parts: string[]) => readFileSync(path.join(process.cwd(), ...parts), "utf-8");
const POSSESSION = JSON.parse(read("public", "data", "learn", "possession.json")) as Record<string, any>;
const FENCE = JSON.parse(read("lib", "learn", "fence.json")) as { held_out: string[]; forbidden_keys: string[] };

// `possession.<path>` is a dotted path into possession.json, a match id after `matches`.
function inFile(dotted: string): unknown {
  const parts = dotted.split(".");
  if (parts[0] !== "possession") return undefined;
  let at: unknown = POSSESSION;
  for (let i = 1; i < parts.length; i++) {
    if (Array.isArray(at) && parts[i - 1] === "matches") at = at.find((m: { match_id: string }) => m.match_id === parts[i]);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[parts[i]] : undefined;
  }
  return at;
}

type Computed = Record<string, any>;
const learn = (page: Page) => page.evaluate(() => window.__learn as Computed);

async function open(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(ROUTE);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("How often does possession change hands?");
  if (EXPOSED) await expect.poll(() => page.evaluate(() => Boolean(window.__learn?.timeline && window.__learn?.fb))).toBe(true);
  return errors;
}

async function expectFigures(page: Page) {
  const figs = await page.locator("[data-fig]").evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig") ?? "", (e.textContent ?? "").trim()] as const));
  const computed = EXPOSED ? await learn(page) : null;
  const wrong: string[] = [];
  for (const [name, text] of figs) {
    let value: unknown;
    if (name.startsWith("learn.")) {
      if (!computed) continue;
      value = name.slice(6).split(".").reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], computed);
    } else value = inFile(name);
    if (value === undefined) wrong.push(`${name}: not in its source`);
    else if (text !== display(String(value), name)) wrong.push(`${name}: page "${text}", source ${String(value)}`);
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  return figs.length; // what the page prints, whichever build: a test build also checks the learn.* ones
}

test.describe(ROUTE, () => {
  test("every data-fig is the file's or the browser's, before and after the reader acts", async ({ page }) => {
    const errors = await open(page);
    const first = await expectFigures(page);
    expect(first).toBeGreaterThan(100);
    const radios = page.getByRole("radio");
    await expect(radios).toHaveCount(2);
    for (const [k, sport, key] of [[1, "basketball", "bb"], [0, "football", "fb"]] as const) {
      await radios.nth(k).check();
      if (EXPOSED) {
        await expect.poll(async () => (await learn(page)).timeline.sport).toBe(sport);
        const l = await learn(page);
        expect(l.timeline.n).toBe(l[key].n);
        expect(l.timeline.median).toBe(l[key].median);
        expect(l.timeline.beyond2_pct).toBe(l[key].beyond2_pct);
      }
    }
    expect(await expectFigures(page)).toBe(first);
    expect(errors).toEqual([]);
  });

  test("the per-match tables hold the file's rows, and no football match is held out", async ({ page }) => {
    await open(page);
    for (const sport of ["football", "basketball"]) {
      const rows = await page.locator(`figure[data-figure="per-match"] table[data-sport="${sport}"] tr[data-match]`).evaluateAll((els) => els.map((e) => e.getAttribute("data-match")));
      expect(rows).toEqual((POSSESSION[sport].matches as { match_id: string }[]).map((m) => m.match_id));
    }
    const football = (POSSESSION.football.matches as { match_id: string }[]).map((m) => m.match_id.replace(/^fb:/, ""));
    expect(football).toHaveLength(10);
    expect(FENCE.held_out.filter((id) => football.includes(id))).toEqual([]);
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

  test("no forbidden key outside a quote or a citation, no vetted phrase anywhere, no held-out id in the HTML", async ({ page }) => {
    await open(page);
    const all = ((await page.locator("main").textContent()) ?? "").toLowerCase();
    expect(["straight line", "constant speed", "width", "pressure"].filter((w) => all.includes(w))).toEqual([]);
    const text = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      main.querySelectorAll("cite, q").forEach((e) => e.remove());
      return (main.textContent ?? "").toLowerCase();
    });
    expect(FENCE.forbidden_keys.filter((k) => text.includes(k))).toEqual([]);
    expect(text).not.toContain("time to impact");
    const html = await (await page.request.get(ROUTE)).text();
    expect(html.length).toBeGreaterThan(10_000);
    expect(FENCE.held_out.filter((id) => html.includes(id))).toEqual([]);
  });

  test("the lesson weighs under 400,000 bytes with everything", async ({ page }) => {
    let bytes = 0;
    const sizes: Promise<void>[] = [];
    page.on("requestfinished", (r) =>
      sizes.push(
        r.sizes().then((s) => {
          bytes += s.responseBodySize + s.responseHeadersSize;
        }),
      ),
    );
    await page.goto(ROUTE);
    await page.waitForLoadState("networkidle");
    await Promise.all(sizes);
    console.log(`${ROUTE}: ${bytes} bytes transferred`);
    expect(bytes).toBeLessThan(400_000);
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
    const scripts = await page
      .locator("main msub > :last-child, main msup > :last-child")
      .evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
    expect(scripts.length).toBeGreaterThan(0);
    expect(Math.min(...scripts)).toBeGreaterThanOrEqual(16);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `possession-${width}.png`), fullPage: true });
  });
}
