import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";
import { display } from "../lib/learn/display";

// Lesson 12 (task 117) in the browser. Every figure is read back from expected-points.json on
// disk, and the ones the page computes are computed again here from its counts, never typed:
// the head panel, the tables and their intervals (task 117b), "Run it here", the attribution, and
// the floors of P13.
const expect = baseExpect.configure({ timeout: 20_000 });

const ROUTE = "/learn/expected-points";
const EXPOSED = !process.env.BASE_URL;
const SHOTS = process.env.LEARN_SHOTS; // a folder for full-page captures to look at, if set
const EUROLEAGUE_HREF = "https://www.euroleaguebasketball.net/euroleague/";

interface Tally {
  n: number;
  made: number;
  pts: number;
}
const CLASSES = ["rim", "mid", "three"] as const;
type Zones = Record<(typeof CLASSES)[number], Tally>;
interface Team extends Zones {
  code: string;
  name: string;
  pps: number;
  xpps: number;
  mix: number;
  making: number;
  mix_ci: [number, number];
  making_ci: [number, number];
}
interface Season {
  season: string;
  league: Zones;
  pps: Record<string, number>;
  mean: number;
  games_ratio: { mix: { median: number } };
  teams: Team[];
}
const FILE = JSON.parse(readFileSync(path.join(process.cwd(), "public", "data", "euroleague", "expected-points.json"), "utf-8")) as {
  source: string;
  level: number;
  z: number;
  seasons: Season[];
} & Record<string, unknown>;

// `xp.<season>.<path>` (a team code after `teams`) or `xp.<path>` from the file's root.
function inFile(name: string): unknown {
  const [prefix, first, ...rest] = name.split(".");
  if (prefix !== "xp") return undefined;
  let at: unknown = FILE.seasons.find((s) => s.season === first) ?? FILE[first];
  rest.forEach((key, i) => {
    if (Array.isArray(at) && rest[i - 1] === "teams") at = at.find((t: Team) => t.code === key);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined;
  });
  return at;
}

// The figures the text computes, worked out again from the file: `learn.season.<season>.<key>`
// and `learn.ex.<key>`.
const round = (x: number, d: number) => Number(x.toFixed(d));
// An interval excludes zero when both bounds are on one side of it, as the file prints them.
const excludes = ([lo, hi]: [number, number]) => lo > 0 || hi < 0;
const width = ([lo, hi]: [number, number]) => hi - lo;
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};
function computed(): Record<string, unknown> {
  const season: Record<string, unknown> = {};
  for (const s of FILE.seasons) {
    const lo = (f: "mix" | "making") => s.teams.reduce((a, t) => (t[f] < a[f] ? t : a));
    const hi = (f: "mix" | "making") => s.teams.reduce((a, t) => (t[f] > a[f] ? t : a));
    const range = (f: "mix" | "making") => round(hi(f)[f] - lo(f)[f], 3);
    season[s.season] = {
      pct: Object.fromEntries(CLASSES.map((c) => [c, round((100 * s.league[c].made) / s.league[c].n, 1)])),
      value: Object.fromEntries(CLASSES.map((c) => [c, round(s.league[c].pts / s.league[c].made, 0)])),
      plain: round(CLASSES.reduce((a, c) => a + s.league[c].pts / s.league[c].n, 0) / 3, 3),
      teams: s.teams.length,
      mix_lo: lo("mix").mix,
      mix_lo_code: lo("mix").code,
      mix_hi: hi("mix").mix,
      mix_hi_code: hi("mix").code,
      mix_range: range("mix"),
      making_lo: lo("making").making,
      making_lo_code: lo("making").code,
      making_hi: hi("making").making,
      making_hi_code: hi("making").code,
      making_range: range("making"),
      ratio: round(range("making") / range("mix"), 1),
      making_pos: s.teams.filter((t) => t.making > 0).length,
      excl_mix: s.teams.filter((t) => excludes(t.mix_ci)).length,
      excl_making: s.teams.filter((t) => excludes(t.making_ci)).length,
      chance: round((1 - FILE.level) * s.teams.length, 1),
      width_ratio: round(median(s.teams.map((t) => width(t.making_ci))) / median(s.teams.map((t) => width(t.mix_ci))), 1),
      wide_mix: s.teams.filter((t) => Math.abs(t.mix) > (s.games_ratio.mix.median * width(t.mix_ci)) / 2).length,
    };
  }
  const first = FILE.seasons[0];
  const ex = first.teams.reduce((a, t) => (t.pps > a.pps ? t : a));
  const n = CLASSES.reduce((a, c) => a + ex[c].n, 0);
  return {
    season,
    ex: { season: first.season, code: ex.code, share: Object.fromEntries(CLASSES.map((c) => [c, round((100 * ex[c].n) / n, 1)])), mix: round(ex.xpps - first.mean, 3), making: round(ex.pps - ex.xpps, 3) },
    level_pct: round(100 * FILE.level, 0),
  };
}
const LEARN = computed();
const pick = (root: unknown, dotted: string) =>
  dotted.split(".").reduce<unknown>((o, k) => (o !== null && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), root);
const seasonLabel = (code: string) => {
  const year = Number(code.slice(1));
  return `${year}-${String((year + 1) % 100).padStart(2, "0")}`;
};

async function open(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(ROUTE);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("How many points is a shot worth?");
  if (EXPOSED) await expect.poll(() => page.evaluate(() => Boolean(window.__learn?.season && window.__learn?.ex))).toBe(true);
  return errors;
}

// Bytes and requests of a page load, the way pages.spec.ts counts them.
async function weigh(page: Page) {
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  const urls: string[] = [];
  page.on("requestfinished", (r) =>
    sizes.push(
      r.sizes().then((s) => {
        bytes += s.responseBodySize + s.responseHeadersSize;
      }),
    ),
  );
  page.on("request", (r) => urls.push(r.url()));
  await page.goto(ROUTE);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  return { bytes, urls };
}

test.describe(ROUTE, () => {
  test("every data-fig is the file's, or computed again here from its counts", async ({ page }) => {
    const errors = await open(page);
    const figs = await page.locator("[data-fig]").evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig") ?? "", (e.textContent ?? "").trim()] as const));
    const browser = EXPOSED ? await page.evaluate(() => window.__learn as Record<string, unknown>) : null;
    const wrong: string[] = [];
    for (const [name, text] of figs) {
      const value = name.startsWith("learn.") ? pick(LEARN, name.slice(6)) : inFile(name);
      if (value === undefined) wrong.push(`${name}: not in its source`);
      else if (text !== display(String(value), name)) wrong.push(`${name}: page "${text}", source ${String(value)}`);
      if (browser && name.startsWith("learn.") && String(pick(browser, name.slice(6))) !== String(value)) wrong.push(`${name}: browser ${String(pick(browser, name.slice(6)))}`);
    }
    expect(wrong.slice(0, 5)).toEqual([]);
    const fromFile = figs.filter(([n]) => n.startsWith("xp.")).length;
    console.log(`${ROUTE}: ${figs.length} figures, ${fromFile} from the file`);
    expect(fromFile).toBeGreaterThan(150);
    expect(figs.length - fromFile).toBeGreaterThan(20);
    expect(errors).toEqual([]);
  });

  test("the tables hold every team of each season, most points per shot first, and name the seasons", async ({ page }) => {
    await open(page);
    for (const s of FILE.seasons) {
      const rows = await page.locator(`table[data-season="${s.season}"] tr[data-team]`).evaluateAll((els) => els.map((e) => e.getAttribute("data-team")));
      expect([...rows].sort()).toEqual(s.teams.map((t) => t.code).sort());
      const pps = rows.map((code) => s.teams.find((t) => t.code === code)!.pps);
      expect(pps).toEqual([...pps].sort((a, b) => b - a));
    }
    const seasons = await page.locator("main [data-season]").evaluateAll((els) => els.filter((e) => e.tagName === "SPAN").map((e) => [e.getAttribute("data-season"), (e.textContent ?? "").trim()]));
    expect(seasons.length).toBeGreaterThan(8);
    for (const [code, text] of seasons) {
      expect(FILE.seasons.map((s) => s.season)).toContain(code);
      expect(text).toBe(seasonLabel(code!));
    }
  });

  test("every team's intervals are the file's, in its row and in its strip", async ({ page }) => {
    await open(page);
    let rows = 0;
    for (const s of FILE.seasons) {
      const got = await page.locator(`table[data-season="${s.season}"] tr[data-team]`).evaluateAll((trs) =>
        trs.map((tr) => ({
          code: tr.getAttribute("data-team")!,
          cells: Array.from(tr.querySelectorAll("td")).map((td) => (td.textContent ?? "").trim()),
          middle: Number(tr.querySelector("svg")!.getAttribute("viewBox")!.split(" ")[2]) / 2,
          // Each interval's line, in the strip's own units: [x1, x2].
          lines: Array.from(tr.querySelectorAll("[data-interval] line:first-child")).map((l) => [Number(l.getAttribute("x1")), Number(l.getAttribute("x2"))]),
        })),
      );
      for (const row of got) {
        const t = s.teams.find((x) => x.code === row.code)!;
        expect(row.cells, row.code).toContain(`${t.mix_ci[0]} to ${t.mix_ci[1]}`);
        expect(row.cells, row.code).toContain(`${t.making_ci[0]} to ${t.making_ci[1]}`);
        // The strip is symmetric about zero, so a bound b sits at its middle plus b times one scale.
        expect(row.lines).toHaveLength(2);
        const [mixLine, makingLine] = row.lines;
        const mid = (mixLine[0] * t.mix_ci[1] - mixLine[1] * t.mix_ci[0]) / (t.mix_ci[1] - t.mix_ci[0]);
        const scale = (mixLine[1] - mixLine[0]) / width(t.mix_ci);
        expect(mid, `${row.code} zero`).toBeCloseTo(row.middle, 6);
        expect(makingLine[0], `${row.code} making from`).toBeCloseTo(row.middle + scale * t.making_ci[0], 6);
        expect(makingLine[1], `${row.code} making to`).toBeCloseTo(row.middle + scale * t.making_ci[1], 6);
        rows++;
      }
    }
    expect(rows).toBe(FILE.seasons.reduce((a, s) => a + s.teams.length, 0));
    const counts = FILE.seasons.map((s) => `${s.season}: making ${s.teams.filter((t) => excludes(t.making_ci)).length}, mix ${s.teams.filter((t) => excludes(t.mix_ci)).length} of ${s.teams.length}`);
    console.log(`${ROUTE}: ${rows} rows with their intervals; exclude zero ${counts.join("; ")}`);
    for (const s of FILE.seasons) {
      for (const key of ["excl_making", "excl_mix"]) {
        await expect(page.locator(`[data-fig="learn.season.${s.season}.${key}"]`).first()).toHaveText(String(pick(LEARN, `season.${s.season}.${key}`)));
      }
    }
  });

  test("the head panel counts up to the first season's points per attempt by class", async ({ page }) => {
    const [first] = FILE.seasons;
    const expected = [first.pps.rim, first.pps.three, first.pps.mid].map(String);
    const html = await (await page.request.get(ROUTE)).text();
    const panel = html.slice(html.indexOf('data-head-panel="result"'), html.indexOf("</figure>", html.indexOf('data-head-panel="result"')));
    for (const v of expected) expect(panel, `${v} in the server's HTML`).toContain(`>${v}<`);
    await page.goto(ROUTE);
    const counts = page.locator(".head-panel [data-count]");
    await expect.poll(() => counts.evaluateAll((els) => els.length > 0 && els.every((e) => e.getAttribute("data-count") === "done")), { timeout: 10_000 }).toBe(true);
    const shown = await page.locator(".head-panel [data-head-readout]").evaluateAll((dds) => dds.map((dd) => (dd.querySelector(":scope > span")?.textContent ?? "").trim()));
    console.log(`${ROUTE}: panel ${JSON.stringify(shown)}, file ${JSON.stringify(expected)}`);
    expect(shown).toEqual(expected);
  });

  test("Run it here rebuilds the lesson's figures from the counts, and nothing loads before Run", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));
    const { bytes, urls } = await weigh(page);
    console.log(`${ROUTE}: ${bytes} bytes transferred before Run`);
    expect(bytes).toBeLessThan(400_000);
    const isEngine = (u: string) => !u.startsWith("blob:") && (u.endsWith(".wasm") || new URL(u).pathname.startsWith("/duckdb/"));
    expect(urls.filter(isEngine), "engine requested before Run").toEqual([]);
    expect(urls.filter((u) => u.includes("/data/euroleague/")), "an aggregate fetched before Run").toEqual([]);

    const figure = page.locator("figure.run-here");
    await figure.getByRole("button", { name: "Run", exact: true }).click();
    await expect(figure).toHaveAttribute("data-query", /^(done|error)$/, { timeout: 120_000 });
    expect(await figure.getAttribute("data-error")).toBeNull();
    const n = Number(await figure.getAttribute("data-figures"));
    // Each class of each season, the two means, and the four figures and four bounds of every team.
    expect(n).toBe(FILE.seasons.reduce((a, s) => a + 3 + 2 + 8 * s.teams.length, 0));
    await expect(figure).toHaveAttribute("data-matched", String(n));
    if (EXPOSED) expect(await page.evaluate(() => (window.__learn as { reproduce?: unknown }).reproduce)).toMatchObject({ matched: n, n });
    const data = urls.filter((u) => u.includes("/data/"));
    expect(data.every((u) => new URL(u).pathname === "/data/euroleague/expected-points.json"), data.join(" ")).toBe(true);
    console.log(`${ROUTE}: ${n} of ${n} rows match; engine ${await figure.getAttribute("data-bytes-engine")} B, data ${await figure.getAttribute("data-bytes-data")} B`);
    expect(errors).toEqual([]);
  });

  test("the prose has no digit once figures, seasons, formulas, quotes, code, tables and the contact are out", async ({ page }) => {
    await open(page);
    const digits = await page.evaluate(() => {
      const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
      main.querySelectorAll("[data-fig], [data-series-n], [data-season], math, cite, q, code, pre, table, figure, textarea, a[href^='mailto:']").forEach((e) => e.remove());
      return (main.textContent ?? "").match(/.{0,30}\d+.{0,30}/g) ?? [];
    });
    expect(digits).toEqual([]);
  });

  test("it names its source, says it is not affiliated, and asks nothing of EuroLeague", async ({ page }) => {
    const hosts: string[] = [];
    page.on("request", (r) => hosts.push(new URL(r.url()).host));
    await open(page);
    await expect(page.locator('[data-attribution="source"]')).toHaveText(`Data: ${FILE.source}.`);
    await expect(page.locator('[data-attribution="source"] a')).toHaveAttribute("href", EUROLEAGUE_HREF);
    await expect(page.locator('[data-attribution="affiliation"]')).toHaveText("Not affiliated with EuroLeague.");
    await page.waitForLoadState("networkidle");
    expect(hosts.filter((h) => h.includes("euroleague"))).toEqual([]);
  });
});

for (const width of [390, 1440]) {
  test(`${ROUTE} at ${width} px: no sideways scroll, nothing under 16 px, no figures overlapping`, async ({ page }) => {
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
    const scripts = await page.locator("main msub > :last-child").evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
    expect(scripts.length).toBeGreaterThan(0);
    expect(Math.min(...scripts)).toBeGreaterThanOrEqual(16);
    const overlaps = await page.evaluate(() => {
      const boxes = Array.from(document.querySelectorAll("main figure")).map((f) => f.getBoundingClientRect());
      const out: string[] = [];
      boxes.forEach((a, i) => boxes.slice(i + 1).forEach((b, j) => a.left < b.right && b.left < a.right && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5 && out.push(`${i} and ${i + j + 1}`)));
      return out;
    });
    expect(overlaps).toEqual([]);
    if (SHOTS) {
      const counts = page.locator(".head-panel [data-count]");
      await expect.poll(() => counts.evaluateAll((els) => els.length > 0 && els.every((e) => e.getAttribute("data-count") === "done"))).toBe(true);
      await page.screenshot({ path: path.join(SHOTS, `expected-points-${width}.png`), fullPage: true });
      await page.locator('section[aria-labelledby="teams-h"]').screenshot({ path: path.join(SHOTS, `expected-points-teams-${width}.png`) });
    }
  });
}

test("with reduced motion the panel stands still at its figures and nothing animates after load", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
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
  await open(page);
  await page.waitForLoadState("networkidle");
  const counts = page.locator(".head-panel [data-count]");
  await expect.poll(() => counts.evaluateAll((els) => els.map((e) => e.getAttribute("data-count")))).toEqual(["still"]);
  const [first] = FILE.seasons;
  await expect(page.locator('.head-panel [data-head-readout="0"] > span').first()).toHaveText(String(first.pps.rim));
  const settled = () =>
    page.evaluate(
      () =>
        new Promise<{ pending: number; calls: number }>((resolve) => {
          const w = window as unknown as { __raf: { pending: Set<number>; calls: number }; __rafOriginal: typeof requestAnimationFrame };
          w.__rafOriginal(() => w.__rafOriginal(() => resolve({ pending: w.__raf.pending.size, calls: w.__raf.calls })));
        }),
    );
  await settled();
  const a = await settled();
  const b = await settled();
  expect(a.pending, "callbacks waiting").toBe(0);
  expect(b.calls, "callbacks scheduled while idle").toBe(a.calls);
  const animated = await page.evaluate(() => Array.from(document.querySelectorAll("main *")).filter((e) => getComputedStyle(e).animationName !== "none").length);
  expect(animated).toBe(0);
});
