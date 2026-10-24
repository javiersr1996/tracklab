import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";

// Lesson 5 end to end: every `data-fig` against the published file it names or against
// `window.__learn`, the prose without digits, and the page at a phone's width and a desktop's.
const expect = baseExpect.configure({ timeout: 20_000 });
const CADENCE = "/learn/cadence";
// `window.__learn` exists in dev and test builds, not against a deployment.
const EXPOSED = !process.env.BASE_URL;

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

async function open(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(CADENCE);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("How many steps per second?");
  if (EXPOSED) await expect.poll(() => page.evaluate(() => Boolean(window.__learn?.hook && window.__learn?.lag && window.__learn?.noise && window.__learn?.player))).toBe(true);
  return errors;
}

async function expectFigures(page: Page) {
  const figs = await page.locator("[data-fig]").evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig") ?? "", (e.textContent ?? "").trim()] as const));
  const learn = EXPOSED ? await page.evaluate(() => window.__learn) : null;
  const wrong: string[] = [];
  let fromFile = 0;
  let fromBrowser = 0;
  for (const [name, text] of figs) {
    if (name.startsWith("learn.")) {
      if (!learn) continue;
      fromBrowser++;
      const value = dotted(learn, name.slice(6));
      if (value === undefined || text !== String(value)) wrong.push(`${name}: page "${text}", browser ${String(value)}`);
    } else {
      fromFile++;
      const value = inFile(name);
      if (value === undefined || text !== String(value)) wrong.push(`${name}: page "${text}", file ${String(value)}`);
    }
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  return { fromFile, fromBrowser };
}

test("every data-fig is its file's or the browser's, before and after the reader acts", async ({ page }) => {
  const errors = await open(page);
  const first = await expectFigures(page);
  expect(first.fromFile).toBeGreaterThan(30);
  if (EXPOSED) expect(first.fromBrowser).toBeGreaterThan(40);

  await page.getByRole("slider", { name: "Lag k" }).fill("7");
  await page.getByRole("button", { name: "Add 20 noisy copies" }).click();
  await page.getByLabel("2", { exact: true }).check();
  await page.getByRole("radio", { name: String(inFile("pose.json:protocol.confirmation")) }).check();
  await page.getByRole("slider", { name: "Player" }).fill("5");
  if (EXPOSED) {
    await expect.poll(() => page.evaluate(() => (window.__learn as { noise: { draws: number } }).noise.draws)).toBe(20);
    await expect.poll(() => page.evaluate(() => (window.__learn as { lag: { k: number } }).lag.k)).toBe(7);
    await expect.poll(() => page.evaluate(() => (window.__learn as { player: { index: number } }).player.index)).toBe(5);
  }
  const after = await expectFigures(page);
  expect(after.fromFile).toBe(first.fromFile);
  console.log(`${CADENCE}: ${after.fromFile} figures from the files, ${after.fromBrowser} from the browser`);
  expect(errors).toEqual([]);
});

test("the prose has no digit once figures, formulas, citations, quotes, code and tables are out", async ({ page }) => {
  await page.goto(CADENCE);
  const digits = await page.evaluate(() => {
    const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
    main.querySelectorAll("[data-fig], [data-series-n], math, cite, q, code, pre, table, figure").forEach((e) => e.remove());
    return (main.textContent ?? "").match(/.{0,30}\d+.{0,30}/g) ?? [];
  });
  expect(digits).toEqual([]);
});

test("no forbidden key outside a quote, no held-out id, and under 400,000 bytes", async ({ page }) => {
  const html = await (await page.request.get(CADENCE)).text();
  expect(FENCE.held_out.filter((id) => html.includes(id))).toEqual([]);
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  page.on("requestfinished", (r) => sizes.push(r.sizes().then((s) => void (bytes += s.responseBodySize + s.responseHeadersSize))));
  await page.goto(CADENCE);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  console.log(`${CADENCE}: ${bytes} bytes transferred`);
  expect(bytes).toBeLessThan(400_000);
  const text = await page.evaluate(() => {
    const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
    main.querySelectorAll("cite, q").forEach((e) => e.remove());
    return (main.textContent ?? "").toLowerCase();
  });
  expect(FENCE.forbidden_keys.filter((k) => text.includes(k))).toEqual([]);
});

for (const width of [390, 1440]) {
  test(`${CADENCE} at ${width} px: no sideways scroll, nothing under 16 px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await open(page);
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
    // A capture to look at, not an assertion.
    await page.screenshot({ path: testInfo.outputPath(`cadence-${width}.png`), fullPage: true });
  });
}
