import { expect, type Request, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Task 132: /engineering/history against `history.json` and `platform.json`, read here straight from
// the files and computed with this spec's own code, not the app's helpers, so a duration or a run
// changed in the JSON after the build shows up as a disagreement.
// Mutations checked by hand against a server built before them, each reverted with git: silver of
// run 20261102T185124Z_5caf04b from 206.1 to 106.1 s in history.json fails "each step's dots"; the
// entry 20261102T160222Z_e64b68f deleted fails "every run", "each selection", "each step's dots"
// and "the P16 figures".

interface Step {
  step_key: string;
  status: string;
  duration_ms: number | null;
  incremental: { mode: string; reason: string } | null;
  dbt: { tests: Record<string, number> } | null;
}
interface Entry {
  id: string;
  select: string | null;
  wall_seconds: number;
  steps: Step[];
  quality: {
    dbt: { tests: Record<string, number> | null };
    contracts: { files: number | null; executed: boolean | null; status: string | null; passed: number | null; failed: number | null; skipped: number | null; errors: number | null };
  };
}
const read = (name: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data", name), "utf-8"));
const history = read("history.json") as { entries: Entry[] };
const platform = read("platform.json") as {
  run: { finished_utc: string };
  freshness: { published_utc: string; partitions: { layer: string; table: string; written_utc: string }[] };
};
const entries = [...history.entries].sort((a, b) => a.id.localeCompare(b.id));

const modeOf = (s: Step) => s.incremental?.mode ?? "none";
const med = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const sum = (t: Record<string, number> | null) => (t ? Object.values(t).reduce((a, b) => a + b, 0) : null);

const bySelect = new Map<string, Entry[]>();
for (const e of entries) bySelect.set(e.select ?? "complete", [...(bySelect.get(e.select ?? "complete") ?? []), e]);

test("every run of history.json is a row of the quality chart, in order, with its dbt and contract tests", async ({ page }) => {
  await page.goto("/engineering/history");
  const rows = page.locator("[data-quality] [data-run]");
  await expect(rows).toHaveCount(entries.length);
  expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-run")))).toEqual(entries.map((e) => e.id));
  for (const e of entries) {
    const row = page.locator(`[data-quality] [data-run="${e.id}"]`);
    const total = sum(e.quality.dbt.tests);
    await expect(row).toHaveAttribute("data-dbt", total === null ? "no data" : String(total));
    const c = e.quality.contracts;
    if (c.executed === true) await expect(row).toHaveAttribute("data-contracts", new RegExp(`^${c.passed} passed`));
    else if (c.executed === false) await expect(row).toHaveAttribute("data-contracts", c.status ?? "not run");
    else await expect(row).toHaveAttribute("data-contracts", /run: no data$/);
    // A missing count is never drawn as a zero: "not run (skip)" when every dbt step skipped, else "no data".
    const dbtSteps = e.steps.filter((s) => s.incremental);
    const skipped = dbtSteps.length > 0 && dbtSteps.every((s) => s.incremental!.mode === "skip");
    if (total === null) await expect(row).toContainText(skipped ? "not run (skip)" : "no data");
  }
});

test("each selection is its own series: charted with two runs or more, listed with one", async ({ page }) => {
  await page.goto("/engineering/history");
  const charted = [...bySelect.entries()].filter(([, runs]) => runs.length >= 2);
  const once = [...bySelect.entries()].filter(([, runs]) => runs.length === 1);
  await expect(page.locator("[data-series]")).toHaveCount(charted.length);
  for (const [select, runs] of charted) {
    await expect(page.locator(`[data-series="${select}"]`)).toHaveAttribute("data-runs", String(runs.length));
  }
  expect(await page.locator("[data-once] tr[data-run]").evaluateAll((els) => els.map((e) => e.getAttribute("data-run")).sort())).toEqual(
    once.map(([, runs]) => runs[0].id).sort(),
  );
});

test("each step's dots are its runs' seconds, and the median, threshold and verdict follow from them", async ({ page }) => {
  await page.goto("/engineering/history");
  let checked = 0;
  for (const [select, runs] of [...bySelect.entries()].filter(([, r]) => r.length >= 2)) {
    const series = page.locator(`[data-series="${select}"]`);
    const keys = [...new Set(runs.flatMap((e) => e.steps.map((s) => s.step_key)))];
    for (const key of keys) {
      const ran = runs.flatMap((e) =>
        e.steps.filter((s) => s.step_key === key && s.status === "success" && s.duration_ms !== null).map((s) => ({ id: e.id, s })),
      );
      if (!ran.length) continue;
      const row = series.locator(`[data-step="${key}"]`);
      const dots = await row.locator("circle[data-run]").evaluateAll((els) =>
        els.map((c) => [c.getAttribute("data-run"), c.getAttribute("data-seconds")]),
      );
      expect(dots, `${select} ${key}`).toEqual(ran.map(({ id, s }) => [id, (s.duration_ms! / 1000).toFixed(1)]));
      const last = ran[ran.length - 1].s;
      const earlier = ran
        .slice(0, -1)
        .filter(({ s }) => modeOf(s) === modeOf(last))
        .map(({ s }) => s.duration_ms! / 1000);
      const m = earlier.length >= 2 ? med(earlier) : null;
      const t = m === null ? null : m + Math.max(...earlier) - Math.min(...earlier);
      const lastSeconds = last.duration_ms! / 1000;
      await expect(row).toHaveAttribute("data-mode", modeOf(last));
      await expect(row).toHaveAttribute("data-median", m === null ? "" : m.toFixed(1));
      await expect(row).toHaveAttribute("data-threshold", t === null ? "" : t.toFixed(1));
      await expect(row).toHaveAttribute("data-last", lastSeconds.toFixed(1));
      await expect(row).toHaveAttribute("data-verdict", t === null ? "too few" : lastSeconds > t ? "above" : "within");
      if (last.incremental) await expect(series.locator(`[data-reason="${key}"]`)).toContainText(last.incremental.reason);
      checked++;
    }
  }
  console.log(`/engineering/history: ${checked} step series checked against history.json`);
  expect(checked).toBeGreaterThan(0);
});

test("the P16 figures are the silver medians by mode of the selection that ran all three", async ({ page }) => {
  const runs = [...bySelect.values()].find((r) => {
    const modes = new Set(r.flatMap((e) => e.steps.filter((s) => s.step_key === "silver").map(modeOf)));
    return ["full", "skip", "incremental"].every((m) => modes.has(m));
  })!;
  const silver = (mode: string) =>
    med(runs.flatMap((e) => e.steps.filter((s) => s.step_key === "silver" && modeOf(s) === mode).map((s) => s.duration_ms! / 1000)));
  await page.goto("/engineering/history");
  for (const mode of ["full", "skip", "incremental"]) {
    await expect(page.locator(`[data-p16] [data-field="silver.${mode}"]`)).toHaveText(silver(mode).toFixed(1));
  }
  const complete = bySelect.get("complete")!;
  const last = complete[complete.length - 1];
  await expect(page.locator('[data-p16] [data-field="complete.wall"]')).toHaveText(last.wall_seconds.toFixed(1));
  const longest = Math.max(...last.steps.map((s) => s.duration_ms ?? 0)) / 1000;
  await expect(page.locator('[data-p16] [data-field="complete.longest"]')).toHaveText(longest.toFixed(1));
  // The page never says the whole build got faster.
  await expect(page.locator("main")).not.toContainText(/build (is|got|became) faster|faster build/i);
});

test("freshness: the age at publish of each silver and gold directory and of the run", async ({ page }) => {
  const at = new Date(platform.freshness.published_utc).getTime();
  const ages = (f: (p: { layer: string; table: string }) => boolean) =>
    platform.freshness.partitions.filter(f).map((p) => (at - new Date(p.written_utc).getTime()) / 1000);
  const rows: [string, number[]][] = [
    ["silver-frames", ages((p) => p.layer === "silver" && p.table === "frames")],
    ["silver-events", ages((p) => p.layer === "silver" && p.table === "events")],
    ["silver-whole", ages((p) => p.layer === "silver" && p.table !== "frames" && p.table !== "events")],
    ["gold", ages((p) => p.layer === "gold")],
    ["run", [(at - new Date(platform.run.finished_utc).getTime()) / 1000]],
  ];
  await page.goto("/engineering/history");
  for (const [key, a] of rows) {
    const row = page.locator(`[data-fresh-row="${key}"]`);
    await expect(row).toHaveAttribute("data-count", String(a.length));
    const per = { min: 60, h: 3600, d: 86400 }[(await row.getAttribute("data-unit")) as "min" | "h" | "d"];
    await expect(row).toHaveAttribute("data-min", (Math.min(...a) / per).toFixed(1));
    await expect(row).toHaveAttribute("data-max", (Math.max(...a) / per).toFixed(1));
  }
  await expect(page.locator('[data-field="published"]')).toContainText(platform.freshness.published_utc.slice(0, 10));
});

test("under 400,000 bytes, no error, no sideways scroll at 390 px, text 16 px or more", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests: Request[] = [];
  const errors: string[] = [];
  page.on("requestfinished", (r) => requests.push(r));
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/engineering/history");
  await page.waitForLoadState("networkidle");
  let transferred = 0;
  for (const r of requests) {
    const sizes = await r.sizes();
    transferred += sizes.responseBodySize + sizes.responseHeadersSize;
  }
  console.log(`/engineering/history: ${transferred} bytes transferred`);
  expect(transferred).toBeLessThan(400_000);
  expect(errors).toEqual([]);
  const m = await page.evaluate(() => ({
    over: document.documentElement.scrollWidth - window.innerWidth,
    boxes: [...document.querySelectorAll("[data-strips], [data-quality], [data-freshness]")].map((b) => b.scrollWidth > b.clientWidth),
    small: [...document.querySelectorAll("main p, main li, main h3")]
      .filter((e) => (e as HTMLElement).offsetParent && parseFloat(getComputedStyle(e).fontSize) < 16)
      .map((e) => e.textContent?.slice(0, 40)),
  }));
  expect(m.over).toBeLessThanOrEqual(0);
  expect(m.boxes.every(Boolean), "each chart scrolls inside its own box").toBe(true);
  expect(m.small).toEqual([]);
  for (const sel of ["[data-strips]", "[data-quality]", "[data-freshness]"]) {
    const box = page.locator(sel).first();
    await expect(box).toHaveAttribute("tabindex", "0");
    await expect(box).toHaveAttribute("role", "region");
  }
});
