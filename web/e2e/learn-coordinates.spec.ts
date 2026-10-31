import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";
import { display } from "../lib/learn/display";

// Lesson 3 in the browser. The figures are read back from the files on disk and from
// `window.__learn`, never typed here.
const expect = baseExpect.configure({ timeout: 20_000 });
const ROUTE = "/learn/coordinates";
const EXPOSED = !process.env.BASE_URL;
// Where the captures go: SHOTS_DIR when set, the test's own output folder otherwise.
const SHOTS = process.env.SHOTS_DIR;

const read = (...parts: string[]) => JSON.parse(readFileSync(path.join(process.cwd(), ...parts), "utf-8"));
const FENCE = read("lib", "learn", "fence.json") as { held_out: string[]; forbidden_keys: string[] };
const STATS = read("public", "data", "stats.json") as { tables: { table: string; sport: string; match_id: string; rows: number }[] };
const QUALITY = read("public", "data", "quality.json") as Record<string, unknown> & {
  checks: Record<string, { match_id: string; metric: string; value: number; n: number }[]>;
};

const dig = (o: unknown, keys: string[]) =>
  keys.reduce<unknown>((at, k) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[k] : undefined), o);

// `stats.<table>.<match or sport>.rows`, `quality.<check>.<match>.<metric>[.n]`,
// `quality.summary.<...>` and `possession.<stem>.<path>`, read from the files themselves.
function inFile(name: string): unknown {
  const [file, ...parts] = name.split(".");
  if (file === "stats") {
    const [table, key] = parts;
    return STATS.tables.find((r) => r.table === table && (r.match_id === key || (r.match_id === "" && r.sport === key)))?.rows;
  }
  if (file === "quality" && parts[0] === "summary") return dig(QUALITY, parts);
  if (file === "quality") {
    const row = QUALITY.checks[parts[0]]?.find((r) => r.match_id === parts[1] && r.metric === parts[2]);
    return parts[3] === "n" ? row?.n : row?.value;
  }
  if (file === "possession") return dig(read("public", "data", "possessions", `${parts[0]}.json`), parts.slice(1));
  return undefined;
}

const normalise = (s: string) => s.replace(/,/g, "").replace(/−/g, "-").replace(/^\+/, "");

async function open(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(ROUTE);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Can a court and a pitch share one table?");
  if (EXPOSED) await expect.poll(() => page.evaluate(() => Boolean(window.__learn?.frame && window.__learn?.clock && window.__learn?.foot_m))).toBe(true);
  return errors;
}

async function expectFigures(page: Page) {
  const figs = await page
    .locator("[data-fig]")
    .evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig") ?? "", (e.textContent ?? "").trim()] as const));
  const computed = EXPOSED ? await page.evaluate(() => window.__learn) : null;
  const wrong: string[] = [];
  let fromFile = 0;
  let fromBrowser = 0;
  for (const [name, text] of figs) {
    const learn = name.startsWith("learn.");
    if (learn && !computed) continue;
    const value = learn ? dig(computed, name.slice(6).split(".")) : inFile(name);
    if (learn) fromBrowser++;
    else fromFile++;
    if (value === undefined || normalise(display(String(value), name)) !== normalise(text)) wrong.push(`${name}: page "${text}", source ${String(value)}`);
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  return { fromFile, fromBrowser };
}

test.describe(ROUTE, () => {
  test("every data-fig is its file's or the browser's, before and after the reader acts", async ({ page }) => {
    const errors = await open(page);
    const first = await expectFigures(page);
    expect(first.fromFile).toBeGreaterThan(60);
    if (EXPOSED) expect(first.fromBrowser).toBeGreaterThan(30);

    await page.getByLabel("pitch").check();
    await page.getByLabel("× k, turned for the other team").check();
    await page.getByRole("slider", { name: "Instant" }).fill("333");
    await expect(page.locator('figure[data-figure="frame"]')).toHaveAttribute("data-step", "turn-other");
    if (EXPOSED) {
      await expect.poll(() => page.evaluate(() => (window.__learn?.clock as { t: number }).t)).toBe(333);
      const frame = (await page.evaluate(() => window.__learn?.frame)) as { k: number; sport: string; unit: string };
      expect([frame.k, frame.sport, frame.unit]).toEqual([-1, "football", "m"]);
    }
    const after = await expectFigures(page);
    expect(after.fromFile).toBe(first.fromFile);
    console.log(`${ROUTE}: ${first.fromFile} figures from the files, ${after.fromBrowser} from the browser`);
    expect(errors).toEqual([]);
  });

  test("the prose has no digit once figures, formulas, citations, quotes, code and tables are out", async ({ page }) => {
    await open(page);
    const digits = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      main.querySelectorAll("[data-fig], [data-series-n], math, cite, q, code, pre, table, figure").forEach((e) => e.remove());
      return (main.textContent ?? "").match(/.{0,30}\d+.{0,30}/g) ?? [];
    });
    expect(digits).toEqual([]);
  });

  test("no held-out match id in the HTML, no forbidden key outside a quote or citation", async ({ page }) => {
    const html = await (await page.request.get(ROUTE)).text();
    expect(html.length).toBeGreaterThan(10_000);
    expect(FENCE.held_out.filter((id) => html.includes(id))).toEqual([]);
    await open(page);
    const text = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      main.querySelectorAll("cite, q").forEach((e) => e.remove());
      return (main.textContent ?? "").toLowerCase();
    });
    expect(FENCE.forbidden_keys.filter((k) => text.includes(k))).toEqual([]);
  });

  test("weighs under 400,000 bytes with everything", async ({ page }) => {
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

  test("nothing starts by itself: no requestAnimationFrame waits after load", async ({ page }) => {
    type Raf = { __raf: { pending: Set<number>; calls: number }; __rafOriginal: typeof requestAnimationFrame };
    await page.addInitScript(() => {
      const w = window as unknown as Raf;
      w.__raf = { pending: new Set(), calls: 0 };
      const original = window.requestAnimationFrame.bind(window);
      w.__rafOriginal = original;
      window.requestAnimationFrame = (cb) => {
        w.__raf.calls++;
        const id = original((t) => {
          w.__raf.pending.delete(id);
          cb(t);
        });
        w.__raf.pending.add(id);
        return id;
      };
    });
    await open(page);
    await page.waitForLoadState("networkidle");
    // The head panel's count (task 112) is the one motion on load, and it lands: wait for it.
    const counts = page.locator(".head-panel [data-count]");
    await expect.poll(() => counts.evaluateAll((els) => els.length > 0 && els.every((e) => e.getAttribute("data-count") === "done"))).toBe(true);
    // Two frames of the browser's own clock, not the wrapped one.
    const settled = () =>
      page.evaluate(
        () =>
          new Promise<{ pending: number; calls: number }>((resolve) => {
            const w = window as unknown as Raf;
            w.__rafOriginal(() => w.__rafOriginal(() => resolve({ pending: w.__raf.pending.size, calls: w.__raf.calls })));
          }),
      );
    await settled();
    const a = await settled();
    const b = await settled();
    expect(a.pending).toBe(0);
    expect(b.calls).toBe(a.calls);
  });
});

for (const width of [390, 1440]) {
  test(`${ROUTE} at ${width} px: no sideways scroll, nothing under 16 px, controls inside the window`, async ({ page }, testInfo) => {
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

    const outside = await page.locator("main figure .controls input, main figure .controls label").evaluateAll((els) =>
      els.filter((e) => {
        const r = e.getBoundingClientRect();
        return r.right > window.innerWidth + 0.5 || r.left < -0.5;
      }).length,
    );
    expect(outside).toBe(0);
    const file = `coordinates-${width}.png`;
    await page.screenshot({ path: SHOTS ? path.join(SHOTS, file) : testInfo.outputPath(file), fullPage: true });
  });
}
