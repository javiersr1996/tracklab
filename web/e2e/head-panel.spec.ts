import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, test } from "@playwright/test";

// Task 112: the panel in the head of the learn and SQL lessons. Its figures are read back from the
// published JSON on disk, never typed here: the result of three learn lessons once it has counted,
// the answer and the query of two SQL lessons once typed, both already in the server's HTML, and
// with reduced motion everything still from the first paint.
const expect = baseExpect.configure({ timeout: 20_000 });

const read = (...parts: string[]) => JSON.parse(readFileSync(path.join(process.cwd(), "public", "data", ...parts), "utf-8"));

type Cell = string | number | boolean | null;
const QUALITY = read("quality.json") as { hook: { g_data: number; g_real: number } };
const POSSESSION = read("learn", "possession.json") as {
  football: { matches: { run_median_s: number }[] };
  basketball: { matches: { median_s: number }[] };
};
const COURSE = read("sql", "course.json") as {
  lessons: { slug: string; example: { sql: string; columns: string[]; rows: Cell[][] } }[];
};

const span = (xs: number[]) => [Math.min(...xs), Math.max(...xs)].map(String);

// Per lesson: the strings each line of its panel must print, the first line's counted.
const LEARN: Record<string, string[][]> = {
  "/learn/gravity": [[String(QUALITY.hook.g_data)], [String(QUALITY.hook.g_real)]],
  "/learn/possession": [
    span(POSSESSION.football.matches.map((m) => m.run_median_s)),
    span(POSSESSION.basketball.matches.map((m) => m.median_s)),
  ],
};

// The cell as the worked example's table prints it (`exampleCell` in lib/sql/course.ts).
const cell = (v: Cell) => (v === null ? "NULL" : typeof v === "string" ? v : JSON.stringify(v));

function example(slug: string) {
  const lesson = COURSE.lessons.find((l) => l.slug === slug);
  if (!lesson) throw new Error(`course.json has no lesson ${slug}`);
  const first = lesson.example.rows[0];
  return { sql: lesson.example.sql, answer: `${cell(first[0])} · ${cell(first[first.length - 1])}` };
}

const SQL = ["select", "joins"];

// The panel's part of the server's HTML, so a figure the lesson's prose also prints cannot pass for it.
async function panelHtml(page: Page, route: string, kind: "result" | "query") {
  const html = await (await page.request.get(route)).text();
  const start = html.indexOf(`data-head-panel="${kind}"`);
  expect(start, `a ${kind} panel in ${route}`).toBeGreaterThan(0);
  return html.slice(start, html.indexOf("</figure>", start));
}

// What each line of the panel prints: the counted values of the first, the plain ones of the rest.
async function readouts(page: Page) {
  return page.locator(".head-panel [data-head-readout]").evaluateAll((dds) =>
    dds.map((dd) => Array.from(dd.querySelectorAll(":scope > span:not(.head-to):not(.head-unit)")).map((s) => (s.textContent ?? "").trim())),
  );
}

for (const [route, expected] of Object.entries(LEARN)) {
  test(`${route}: the head panel counts up to the published result`, async ({ page }) => {
    // The server's HTML already holds every figure, for a page without JS.
    const html = await panelHtml(page, route, "result");
    for (const value of expected.flat()) expect(html, `${value} in the server's HTML`).toContain(`>${value}<`);

    await page.goto(route);
    const counts = page.locator(".head-panel [data-count]");
    await expect(counts).toHaveCount(expected[0].length);
    await expect.poll(() => counts.evaluateAll((els) => els.every((e) => e.getAttribute("data-count") === "done")), { timeout: 10_000 }).toBe(true);
    const shown = await readouts(page);
    console.log(`${route}: panel ${JSON.stringify(shown)}, JSON ${JSON.stringify(expected)}`);
    expect(shown).toEqual(expected);
  });
}

for (const slug of SQL) {
  test(`/sql/${slug}: the head panel types the worked example and its answer`, async ({ page }) => {
    const { sql, answer } = example(slug);
    expect(await panelHtml(page, `/sql/${slug}`, "query")).toContain(`>${answer}<`);

    await page.goto(`/sql/${slug}`);
    const panel = page.locator('[data-head-panel="query"]');
    await expect(panel).toHaveAttribute("data-type", "done", { timeout: 10_000 });
    await expect(panel.locator("[data-head-answer]")).toHaveText(answer);
    await expect(panel.locator("[data-head-answer]")).toBeVisible();
    expect(await panel.locator("[data-head-sql]").textContent()).toBe(sql);
    console.log(`/sql/${slug}: panel answer "${answer}"`);
  });
}

test("with reduced motion the panels stand still at their final figures", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/learn/gravity");
  const counts = page.locator(".head-panel [data-count]");
  await expect.poll(() => counts.evaluateAll((els) => els.map((e) => e.getAttribute("data-count")))).toEqual(["still"]);
  expect(await readouts(page)).toEqual(LEARN["/learn/gravity"]);

  const { sql, answer } = example("select");
  await page.goto("/sql/select");
  const panel = page.locator('[data-head-panel="query"]');
  await expect(panel).toHaveAttribute("data-type", "still");
  expect(await panel.locator("[data-head-sql]").textContent()).toBe(sql);
  await expect(panel.locator("[data-head-answer]")).toHaveText(answer);
  await expect(panel.locator("[data-head-answer]")).toBeVisible();
  // The caret does not blink.
  expect(await panel.locator(".head-caret").evaluate((e) => getComputedStyle(e).animationName)).toBe("none");

  // An index's sketch rests on its last frame: the ball of /learn at the end of its arc.
  await page.goto("/learn");
  const ball = page.locator(".head-panel-sketch .pv-fall");
  expect(await ball.evaluate((e) => getComputedStyle(e).animationName)).toBe("none");
});
