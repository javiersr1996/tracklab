import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";

// Eleven workers share one server: the waits are on the page's own state, never on a clock.
const expect = baseExpect.configure({ timeout: 20_000 });

const WIDTHS = [390, 1440];
// `window.__learn` exists in dev and test builds, not against a deployment.
const EXPOSED = !process.env.BASE_URL;
const GRAVITY = "/learn/gravity";

const read = (...parts: string[]) => readFileSync(path.join(process.cwd(), ...parts), "utf-8");
const QUALITY = JSON.parse(read("public", "data", "quality.json")) as Record<string, unknown>;
const FENCE = JSON.parse(read("lib", "learn", "fence.json")) as { held_out: string[]; forbidden_keys: string[] };

// Bytes transferred by a page load, the way the other specs count them.
async function transferred(page: Page, path: string) {
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  page.on("requestfinished", (r) =>
    sizes.push(
      r.sizes().then((s) => {
        bytes += s.responseBodySize + s.responseHeadersSize;
      }),
    ),
  );
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  return bytes;
}

test("the index links the five published lessons, none in preparation and none from after", async ({ page }) => {
  const bytes = await transferred(page, "/learn");
  console.log(`/learn: ${bytes} bytes transferred`);
  expect(bytes).toBeLessThan(400_000);

  const published = page.locator('[data-status="published"]');
  await expect(published).toHaveCount(5);
  await expect(published.getByRole("link", { name: "Does the ball obey gravity?" })).toHaveAttribute("href", "/learn/gravity");
  await expect(published.getByRole("link", { name: "Where does the provider's speed come from?" })).toHaveAttribute("href", "/learn/speed");
  await expect(published.getByRole("link", { name: "Can a court and a pitch share one table?" })).toHaveAttribute("href", "/learn/coordinates");
  await expect(published.getByRole("link", { name: "Who gets to the rebound first?" })).toHaveAttribute("href", "/learn/rebound");
  await expect(published.getByRole("link", { name: "How many steps per second?" })).toHaveAttribute("href", "/learn/cadence");

  await expect(page.locator('[data-status="in-preparation"]')).toHaveCount(0);
  await expect(page.getByText("In preparation")).toHaveCount(0);

  // Lessons 6 and 7 come after the fence: the series stops at 5.
  const numbers = await page.locator("[data-series-n]").evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-series-n"))));
  expect(Math.max(...numbers)).toBeLessThanOrEqual(5);
  expect(numbers).toEqual([...numbers].sort((a, b) => a - b));
});

test("the lesson link opens a page, not a 404", async ({ page }) => {
  await page.goto("/learn");
  await page.getByRole("link", { name: "Does the ball obey gravity?" }).click();
  await expect(page).toHaveURL(/\/learn\/gravity$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Does the ball obey gravity?");
  await expect(page.locator("[data-series-n]")).toHaveText("1");
});

test("the header marks Learn current on the index and on a lesson, and only there", async ({ page }) => {
  const learn = page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: "Learn" });
  for (const path of ["/learn", "/learn/gravity"]) {
    await page.goto(path);
    await expect(learn).toHaveAttribute("aria-current", "page");
    await expect(page.locator('nav[aria-label="Sections"] [aria-current]')).toHaveCount(1);
  }
  await page.goto("/quality");
  await expect(learn).not.toHaveAttribute("aria-current", "page");
});

test("the home page links /learn", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('a[href="/learn"]').first()).toBeVisible();
});

for (const width of WIDTHS) {
  for (const path of ["/", "/learn", "/learn/gravity"]) {
    test(`${path} at ${width} px: no sideways scroll, no overlaps, nothing under 16 px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(sideways, "page wider than the window by").toBeLessThanOrEqual(0);

      // The header too: seven links wrap on a phone and must not collide.
      const links = await page.locator(".site-nav a").evaluateAll((els) =>
        els.map((e) => {
          const r = e.getBoundingClientRect();
          return { x: r.left, y: r.top, r: r.right, b: r.bottom };
        }),
      );
      for (let i = 0; i < links.length; i++) {
        for (let j = i + 1; j < links.length; j++) {
          const a = links[i];
          const b = links[j];
          const overlap = a.x < b.r && b.x < a.r && a.y < b.b && b.y < a.b;
          expect(overlap, `header links ${i} and ${j} overlap`).toBe(false);
        }
      }

      // Text of every element, MathML included, is 16 px or more.
      const small = await page.evaluate(() =>
        Array.from(document.querySelectorAll("main *"))
          .filter((el) =>
            Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""),
          )
          .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
          .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}`),
      );
      expect(small, "text under 16 px").toEqual([]);

      if (path === "/learn/gravity") {
        // The check has to see the scripts, or it protects nothing: every subscript and superscript.
        const scripts = await page
          .locator("main msub > :last-child, main msup > :last-child")
          .evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
        expect(scripts.length).toBeGreaterThan(0);
        expect(Math.min(...scripts)).toBeGreaterThanOrEqual(16);
      }
    });
  }
}

// ---------------------------------------------------------------------------------------------
// Lesson 1 (task 81). The figures are read back from the file on disk and from `window.__learn`,
// never typed here; the prose is checked for what it must not contain.
// ---------------------------------------------------------------------------------------------

// A dotted path in `quality.json`; under `checks.<check>` the next two parts are a match id and a
// metric, the way the file keys its rows (`checks.gravity.bb:114086.g_median` is that row's value).
function inFile(dotted: string): unknown {
  const parts = dotted.split(".");
  if (parts[0] === "checks" && parts.length === 4) {
    const rows = (QUALITY.checks as Record<string, { match_id: string; metric: string; value: number }[]>)[parts[1]];
    return rows?.find((r) => r.match_id === parts[2] && r.metric === parts[3])?.value;
  }
  return parts.reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), QUALITY);
}

type Computed = Record<string, any>;
const learn = (page: Page) => page.evaluate(() => window.__learn as Computed);

async function openLesson(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(GRAVITY);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Does the ball obey gravity?");
  if (EXPOSED) await expect.poll(() => page.evaluate(() => Boolean(window.__learn?.fit && window.__learn?.window && window.__learn?.noise))).toBe(true);
  return errors;
}

// Every `data-fig` on the page, with the text it shows.
const shownFigures = (page: Page) =>
  page.locator("[data-fig]").evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig") ?? "", (e.textContent ?? "").trim()] as const));

// `learn.<key>` figures against what the browser computed (`window.__learn`), every other one
// against the file. Returns how many of each it compared.
async function expectFigures(page: Page) {
  const figs = await shownFigures(page);
  const computed = EXPOSED ? await learn(page) : null;
  const wrong: string[] = [];
  let fromFile = 0;
  let fromBrowser = 0;
  for (const [name, text] of figs) {
    if (name.startsWith("learn.")) {
      if (!computed) continue;
      const value = name.slice(6).split(".").reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], computed);
      fromBrowser++;
      if (value === undefined) wrong.push(`${name}: not in window.__learn`);
      else if (text !== String(value)) wrong.push(`${name}: page "${text}", browser ${String(value)}`);
    } else {
      const value = inFile(name);
      fromFile++;
      if (value === undefined) wrong.push(`${name}: not in quality.json`);
      else if (text !== String(value)) wrong.push(`${name}: page "${text}", file ${String(value)}`);
    }
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  return { fromFile, fromBrowser };
}

test.describe("/learn/gravity", () => {
  test("every data-fig is the file's or the browser's, with and without interaction", async ({ page }) => {
    const errors = await openLesson(page);
    const first = await expectFigures(page);
    expect(first.fromFile).toBeGreaterThan(50);
    if (EXPOSED) expect(first.fromBrowser).toBeGreaterThan(20);

    // The readouts that only exist after the reader acts.
    await page.getByRole("button", { name: "Add 20 noisy flights" }).click();
    await page.getByRole("slider", { name: "Half-window H" }).fill("4");
    await page.getByRole("slider", { name: "Try a g" }).fill("7.25");
    const after = await expectFigures(page);
    expect(after.fromFile).toBe(first.fromFile);
    if (EXPOSED) expect(after.fromBrowser).toBeGreaterThan(first.fromBrowser);
    console.log(`/learn/gravity: ${first.fromFile} figures from the file, ${after.fromBrowser} from the browser`);
    expect(errors).toEqual([]);
  });

  test("the per-match table holds the file's ten rows", async ({ page }) => {
    await openLesson(page);
    const rows = await page.locator("tr[data-match]").evaluateAll((els) => els.map((e) => e.getAttribute("data-match")));
    const inQuality = (QUALITY.checks as { gravity: { sport: string; match_id: string }[] }).gravity
      .filter((r) => r.sport === "basketball")
      .map((r) => r.match_id);
    expect(rows.length).toBe(10);
    expect([...rows].sort()).toEqual([...new Set(inQuality)].sort());
  });

  test("the prose has no digit once figures, formulas, citations, quotes, code and tables are out", async ({ page }) => {
    await openLesson(page);
    const digits = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      main.querySelectorAll("[data-fig], [data-series-n], math, cite, q, code, pre, table, figure").forEach((e) => e.remove());
      return (main.textContent ?? "").match(/.{0,30}\d+.{0,30}/g) ?? [];
    });
    expect(digits).toEqual([]);
  });

  test("the text of main holds none of the fence's forbidden keys outside a quote or a citation", async ({ page }) => {
    for (const route of ["/learn", GRAVITY]) {
      await page.goto(route);
      const text = await page.evaluate(() => {
        const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
        main.querySelectorAll("cite, q").forEach((e) => e.remove());
        return (main.textContent ?? "").toLowerCase();
      });
      expect(text.length).toBeGreaterThan(200);
      expect(FENCE.forbidden_keys.filter((k) => text.includes(k)), route).toEqual([]);
    }
  });

  test("no held-out match id is in the HTML of /learn or of the lesson", async ({ page }) => {
    expect(FENCE.held_out.length).toBe(10);
    for (const route of ["/learn", GRAVITY]) {
      const html = await (await page.request.get(route)).text();
      expect(html.length).toBeGreaterThan(10_000);
      expect(FENCE.held_out.filter((id) => html.includes(id)), route).toEqual([]);
    }
  });

  test("the lesson weighs under 400,000 bytes with everything", async ({ page }) => {
    const bytes = await transferred(page, GRAVITY);
    console.log(`${GRAVITY}: ${bytes} bytes transferred`);
    expect(bytes).toBeLessThan(400_000);
  });

  test("the caption names the shot without its internal prefix", async ({ page }) => {
    await openLesson(page);
    const caption = (await page.locator('figure[data-figure="fit"] figcaption').innerText()).replace(/\s+/g, " ");
    const hook = inFile("hook.shot_id") as string;
    expect(caption).toContain(`Shot ${hook.replace(/^shot-/, "")} of match`);
    expect(caption).not.toContain("shot-");
  });
});

test.describe("/learn/gravity, driven through window.__learn", () => {
  test.skip(!EXPOSED, "window.__learn exists in a test build, not against a deployment");

  test("the first reading is the hook's, and it sits below standard gravity", async ({ page }) => {
    await openLesson(page);
    const l = await learn(page);
    const g = inFile("hook.g_real") as number;
    // P3 publishes g at 4 decimals; the bound is the lesson's own (rounding_bound).
    expect(Math.abs(l.fit.g - (inFile("hook.g_data") as number))).toBeLessThanOrEqual(l.rounding_bound + 0.0001);
    expect(l.fit.g).toBe(l.fit_g);
    expect(l.fit.g).toBeLessThan(g);
    expect(l.window.g).toBe(l.fit_g);
    expect(l.matches).toBe(10);
  });

  test("try a g: the slider moves g, and standard gravity gives that g's RMS", async ({ page }) => {
    await openLesson(page);
    const before = await learn(page);
    await page.getByRole("slider", { name: "Try a g" }).fill("7.25");
    await expect.poll(async () => (await learn(page)).fit.g).toBe(7.25);
    const lower = await learn(page);
    expect(lower.fit.rms_mm).toBeGreaterThan(before.fit.rms_mm);
    expect(lower.fit.residuals_mm).toHaveLength(before.samples);

    await page.getByRole("button", { name: "Standard gravity" }).click();
    await expect.poll(async () => (await learn(page)).fit.g).toBe(inFile("hook.g_real"));
    const standard = await learn(page);
    expect(standard.fit.rms_mm).toBe(standard.g_rms_mm);
    expect(standard.fit.rms_mm).toBeGreaterThan(before.fit.rms_mm);

    await page.getByRole("button", { name: "Least squares" }).click();
    await expect.poll(async () => (await learn(page)).fit.rms_mm).toBe(before.fit.rms_mm);
    console.log(`try a g: RMS ${before.fit.rms_mm} mm at ${before.fit.g}, ${standard.fit.rms_mm} mm at ${standard.fit.g}`);
  });

  test("the half-window H changes g, and the shortest is the figure the text quotes", async ({ page }) => {
    await openLesson(page);
    const full = await learn(page);
    await page.getByRole("slider", { name: "Half-window H" }).fill(String(full.window_h_shortest));
    await expect.poll(async () => (await learn(page)).window.h).toBe(full.window_h_shortest);
    const short = await learn(page);
    expect(short.window.g).toBe(full.window_g_shortest);
    expect(short.window.g).not.toBe(full.window.g);
    expect(short.window.samples).toBe(2 * full.window_h_shortest + 1);
    await expect(page.locator('[data-fig="learn.window.g"]')).toHaveText(String(full.window_g_shortest));
  });

  test("noise: the refits of N noisy flights cluster around standard gravity", async ({ page }) => {
    await openLesson(page);
    const add = page.getByRole("button", { name: "Add 20 noisy flights" });
    for (let k = 1; k <= 5; k++) {
      await add.click();
      await expect.poll(async () => (await learn(page)).noise.flights).toBe(20 * k);
    }
    const n = await learn(page);
    const G = inFile("hook.g_real") as number;
    expect(n.noise.gs).toHaveLength(100);
    await expect(page.locator("[data-flights]")).toHaveAttribute("data-flights", "100");
    const mean = (n.noise.gs as number[]).reduce((s, x) => s + x, 0) / 100;
    // The mean of N refits is within 3 sd/sqrt(N) of the g they were drawn at.
    expect(Math.abs(mean - G)).toBeLessThan((3 * n.noise.sd_formula) / Math.sqrt(100));
    expect(Math.abs(n.noise.sd / n.noise.sd_formula - 1)).toBeLessThan(0.25);

    // A bigger sd widens the same cloud.
    await page.getByLabel("10 cm").check();
    await expect.poll(async () => (await learn(page)).noise.sigma_cm).toBe(10);
    const wide = await learn(page);
    expect(wide.noise.sd).toBeGreaterThan(5 * n.noise.sd);
    await page.getByRole("button", { name: "Clear" }).click();
    await expect.poll(async () => (await learn(page)).noise.flights).toBe(0);
    console.log(`noise: mean ${n.noise.mean} sd ${n.noise.sd} (formula ${n.noise.sd_formula}) at 1 cm; sd ${wide.noise.sd} at 10 cm`);
  });
});

// Nothing starts by itself: after load, no requestAnimationFrame callback is waiting, and none
// is scheduled while two frames pass. The init script runs before the page's own scripts.
for (const reducedMotion of ["no-preference", "reduce"] as const) {
  test(`no requestAnimationFrame is active after load (motion: ${reducedMotion})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion });
    await page.addInitScript(() => {
      const w = window as unknown as { __raf: { pending: Set<number>; calls: number }; __rafOriginal: typeof requestAnimationFrame };
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
    await openLesson(page);
    await page.waitForLoadState("networkidle");
    const settled = () =>
      page.evaluate(
        () =>
          new Promise<{ pending: number; calls: number }>((resolve) => {
            const w = window as unknown as { __raf: { pending: Set<number>; calls: number }; __rafOriginal: typeof requestAnimationFrame };
            // Two frames of the browser's own clock, not the wrapped one.
            w.__rafOriginal(() => w.__rafOriginal(() => resolve({ pending: w.__raf.pending.size, calls: w.__raf.calls })));
          }),
      );
    await settled();
    const a = await settled();
    const b = await settled();
    expect(a.pending, "callbacks waiting").toBe(0);
    expect(b.calls, "callbacks scheduled while idle").toBe(a.calls);
  });
}

for (const width of WIDTHS) {
  test(`/learn/gravity at ${width} px: figures do not overlap and the controls fit`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await openLesson(page);
    const overlaps = await page.evaluate(() => {
      const box = (e: Element) => {
        const r = e.getBoundingClientRect();
        return { l: r.left, t: r.top, r: r.right, b: r.bottom };
      };
      const hit = (a: ReturnType<typeof box>, b: ReturnType<typeof box>) => a.l < b.r - 0.5 && b.l < a.r - 0.5 && a.t < b.b - 0.5 && b.t < a.b - 0.5;
      const out: string[] = [];
      const figures = Array.from(document.querySelectorAll("main figure"));
      figures.forEach((f, i) => {
        for (let j = i + 1; j < figures.length; j++) if (hit(box(f), box(figures[j]))) out.push(`figure ${i} and ${j}`);
        const kids = Array.from(f.querySelectorAll(".controls input, .controls button, .controls label, .controls legend"));
        kids.forEach((a, x) => {
          for (let y = x + 1; y < kids.length; y++) {
            if (!a.contains(kids[y]) && !kids[y].contains(a) && hit(box(a), box(kids[y]))) out.push(`figure ${i}: ${a.textContent?.trim()} and ${kids[y].textContent?.trim()}`);
          }
          const r = box(a);
          if (r.r > window.innerWidth + 0.5 || r.l < -0.5) out.push(`figure ${i}: ${a.textContent?.trim()} leaves the window`);
        });
      });
      return out;
    });
    expect(overlaps).toEqual([]);
    // A capture to look at, not an assertion.
    await page.screenshot({ path: testInfo.outputPath(`gravity-${width}.png`), fullPage: true });
  });
}
