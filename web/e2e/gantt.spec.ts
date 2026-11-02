import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Task 123: the step durations on /engineering. Read straight from `platform.json` and
// `lineage.json`, not through the app's own helpers, so a mutation to them shows up as a disagreement.

interface Step {
  step_key: string;
  duration_ms: number;
  started_utc: string | null;
  finished_utc: string | null;
}
const read = (name: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data", name), "utf-8"));
const platform = read("platform.json") as { steps: Step[]; run: { wall_seconds: number; started_utc: string } };
const lineage = read("lineage.json") as { nodes: { key: string; description: string }[] };

test("one bar per step, each with the seconds platform.json has", async ({ page }) => {
  await page.goto("/engineering");
  const bars = page.locator("[data-gantt-step]");
  await expect(bars).toHaveCount(platform.steps.length);
  for (const s of platform.steps) {
    const bar = page.locator(`[data-gantt-step="${s.step_key}"]`);
    await expect(bar).toHaveAttribute("data-seconds", (s.duration_ms / 1000).toFixed(1));
  }
  await expect(page.locator("[data-gantt]")).toHaveAttribute("data-steps", String(platform.steps.length));
});

// Task 132: with a v2 record each bar ends at its step's last event and is its duration long, and the
// note says why the first event is not its start.
test("with a v2 record each bar ends at its step's last event, its own duration long", async ({ page }) => {
  test.skip(platform.steps.some((s) => s.finished_utc === null), "a v1 record has no step times");
  const t0 = new Date(platform.run.started_utc).getTime();
  await page.goto("/engineering");
  for (const s of platform.steps) {
    const end = (new Date(s.finished_utc!).getTime() - t0) / 1000;
    const bar = page.locator(`[data-gantt-step="${s.step_key}"]`);
    await expect(bar).toHaveAttribute("data-end", end.toFixed(1));
    await expect(bar).toHaveAttribute("data-start", (end - s.duration_ms / 1000).toFixed(1));
    expect(end).toBeLessThanOrEqual(platform.run.wall_seconds);
  }
  const firsts = platform.steps.map((s) => (new Date(s.started_utc!).getTime() - t0) / 1000);
  const note = page.locator("[data-gantt-note]");
  await expect(note).toHaveAttribute("data-placed", "end");
  await expect(note).toContainText(`falls ${Math.min(...firsts).toFixed(1)} to ${Math.max(...firsts).toFixed(1)} s into the run`);
});

test("the longest bar is the widest and none passes the wall-clock axis", async ({ page }) => {
  await page.goto("/engineering");
  const widths = await page.$$eval("[data-gantt-step] rect", (rs) => rs.map((r) => Number(r.getAttribute("width"))));
  const longest = platform.steps.reduce((m, s) => (s.duration_ms > m.duration_ms ? s : m));
  const idx = platform.steps.findIndex((s) => s.step_key === longest.step_key);
  expect(Math.max(...widths)).toBeGreaterThan(0);
  const longestWidth = await page
    .locator(`[data-gantt-step="${longest.step_key}"] rect`)
    .getAttribute("width");
  expect(Number(longestWidth)).toBe(Math.max(...widths));
  expect(idx).toBeGreaterThanOrEqual(0);
  expect(longest.duration_ms / 1000).toBeLessThanOrEqual(platform.run.wall_seconds);
});

test("the Gantt scrolls inside its own box at 390 px, never the page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/engineering");
  const m = await page.evaluate(() => {
    const box = document.querySelector("[data-gantt]") as HTMLElement;
    return {
      page: document.documentElement.scrollWidth,
      view: document.documentElement.clientWidth,
      inner: box.scrollWidth,
      outer: box.clientWidth,
    };
  });
  expect(m.page).toBe(m.view);
  expect(m.inner).toBeGreaterThan(m.outer);
});

test("every lineage node has a description and the panel shows it on selection", async ({ page }) => {
  expect(lineage.nodes.filter((n) => !n.description.trim())).toEqual([]);
  await page.goto("/engineering");
  for (const key of ["bronze_basketball_events_drives", "quality_gravity", "silver_frames"]) {
    const node = lineage.nodes.find((n) => n.key === key)!;
    await page.locator(`[data-node="${key}"]`).click();
    await expect(page.locator("[data-lineage-description]")).toHaveText(node.description.trim());
  }
});

test("the chart scrolls by keyboard and every step is also in a table", async ({ page }) => {
  await page.goto("/engineering");
  const box = page.locator("[data-gantt]");
  await expect(box).toHaveAttribute("tabindex", "0");
  await expect(box).toHaveAttribute("role", "region");
  await expect(box).toHaveAttribute("aria-label", /.+/);
  const table = page.locator("[data-gantt-table]");
  await table.locator("summary").click();
  await expect(table.locator("tbody tr")).toHaveCount(platform.steps.length);
  const first = platform.steps[0];
  await expect(table.locator("tbody tr", { hasText: first.step_key }).first()).toContainText((first.duration_ms / 1000).toFixed(1));
});
