import { expect, type Request, test } from "@playwright/test";

// The table's columns and the places each is printed to (lib/quality.ts imports the JSON, which
// this runner cannot): typed here, so a column dropped there fails here.
const TABLE_METRICS = [
  { check: "detection", metric: "ball_detected_pct", label: "Ball detected", unit: "%", decimals: 1 },
  { check: "detection", metric: "player_detected_pct", label: "Player detected", unit: "%", decimals: 1 },
  { check: "gravity", metric: "g_median", label: "Median g", unit: "m/s²", decimals: 2 },
  { check: "gravity", metric: "g_median_bias_pct", label: "g bias", unit: "%", decimals: 1 },
  { check: "entry_angle", metric: "gap_median_deg", label: "Entry angle gap", unit: "°", decimals: 1 },
  { check: "noise", metric: "ball_player_d2_ratio", label: "Ball/player jitter", unit: "×", decimals: 1 },
  { check: "clock", metric: "clock_step_exact_pct", label: "Clock step exact", unit: "%", decimals: 1 },
];

// No window.__replay here (task 30): the hook animation exposes its own state
// through a DOM attribute instead, so this suite runs the same locally and
// against a deployment (BASE_URL).

interface QualityRow {
  sport: string;
  match_id: string;
  metric: string;
  value: number;
  unit: string;
  n: number;
}

interface QualityJson {
  checks: Record<string, QualityRow[]>;
}

test("the hook animation starts on its own and the table matches quality.json", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  const requests: Request[] = [];
  page.on("requestfinished", (r) => requests.push(r));

  await page.goto("/engineering/quality");

  await expect(page.locator("figure.hook")).toHaveAttribute("data-state", "playing", {
    timeout: 2_000,
  });

  const quality = (await (await page.request.get("/data/quality.json")).json()) as QualityJson;

  const cells = page.locator("td[data-metric]");
  const count = await cells.count();
  expect(count).toBeGreaterThan(0);

  let compared = 0;
  for (let i = 0; i < count; i++) {
    const cell = cells.nth(i);
    const check = await cell.getAttribute("data-check");
    const metric = await cell.getAttribute("data-metric");
    const matchId = await cell.getAttribute("data-match");
    const text = (await cell.textContent())?.trim();

    const expected = quality.checks[check ?? ""]?.find(
      (r) => r.match_id === matchId && r.metric === metric,
    );
    if (!expected) {
      // A check that does not apply to this match (e.g. entry_angle, football):
      // quality.json has no such row, so the cell must stay blank.
      const label = `${check} ${metric} ${matchId} has a value but not in quality.json`;
      expect(text, label).toBeFalsy();
      continue;
    }
    const label = `${check} ${metric} ${matchId} is blank but quality.json has a value`;
    expect(text, label).toBeTruthy();
    // Rounded for reading (task 183), the file's whole value in the title.
    const m = TABLE_METRICS.find((x) => x.check === check && x.metric === metric)!;
    expect(text, `${check} ${metric} ${matchId}`).toBe(expected.value.toFixed(m.decimals));
    expect(await cell.getAttribute("title")).toBe(String(expected.value));
    compared++;
  }
  console.log(`/engineering/quality: ${compared} table cells checked against quality.json`);
  expect(compared).toBeGreaterThan(0);

  await page.waitForLoadState("networkidle");
  let transferred = 0;
  for (const r of requests) {
    const sizes = await r.sizes();
    transferred += sizes.responseBodySize + sizes.responseHeadersSize;
  }
  console.log(`/engineering/quality: ${transferred} bytes transferred`);

  expect(errors).toEqual([]);
});

test("the entry_angle check links to its lesson", async ({ page }) => {
  await page.goto("/engineering/quality");
  await expect(page.locator('p[data-check="entry_angle"] a[href="/learn/entry"]')).toHaveCount(1);
});

const middle = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

// Task 183: a chart per column of the table, a dot per match and sport, each median recomputed here
// from quality.json and compared with the one the page prints; a sport the check has no row of says
// so instead of a dot; the table itself folded away under a summary that counts the matches.
test("each check's chart has a dot per match and sport, and prints the medians of quality.json", async ({ page }) => {
  const quality = (await (await page.request.get("/data/quality.json")).json()) as QualityJson;
  await page.goto("/engineering/quality");
  await expect(page.locator("figure.qchart")).toHaveCount(TABLE_METRICS.length);
  for (const m of TABLE_METRICS) {
    const chart = page.locator(`figure[data-chart="${m.metric}"]`);
    await expect(chart.getByRole("heading", { level: 3 })).toHaveText(`${m.label} (${m.unit})`);
    for (const sport of ["basketball", "football"]) {
      const rows = quality.checks[m.check].filter((r) => r.metric === m.metric && r.sport === sport);
      const row = chart.locator(`.qrow[data-sport="${sport}"]`);
      await expect(row.locator(".qdot")).toHaveCount(rows.length);
      if (rows.length === 0) {
        await expect(row.locator('[data-note="not-applicable"]')).toContainText("Does not apply");
        await expect(row.locator(".qstrip")).toHaveCount(0);
        continue;
      }
      await expect(row.locator("[data-matches]")).toHaveText(String(rows.length));
      await expect(row.locator("[data-median]")).toHaveText(middle(rows.map((r) => r.value)).toFixed(m.decimals));
      const plotted = await row.locator(".qdot").evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-value"))).sort((a, b) => a - b));
      expect(plotted, `${m.metric} ${sport}`).toEqual(rows.map((r) => r.value).sort((a, b) => a - b));
    }
  }
  // The basketball ball's zeros are a flag, said in so many words.
  const ball = page.locator('figure[data-chart="ball_detected_pct"] .qrow[data-sport="basketball"]');
  await expect(ball.locator('[data-note="flag"]')).toContainText("the flag is false for the basketball ball in every frame");
  await expect(page.locator('figure[data-chart="g_median"] [data-reference]')).toHaveAttribute("data-reference", String(9.80665));

  const table = page.locator("details[data-quality-table]");
  await expect(table).not.toHaveAttribute("open", "");
  const matches = new Set(Object.values(quality.checks).flatMap((rows) => rows.map((r) => `${r.sport}|${r.match_id}`))).size;
  await expect(table.locator("summary")).toHaveText(`All ${matches} matches, as a table`);
  await expect(table.locator("tbody tr")).toHaveCount(matches);
  await table.locator("summary").click();
  await expect(table.locator("table")).toBeVisible();
});

for (const width of [390, 1440]) {
  test(`at ${width} px the charts keep their dots inside the card and their text 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/engineering/quality");
    for (const chart of await page.locator("figure.qchart").all()) {
      const card = (await chart.boundingBox())!;
      const boxes = await chart.locator(".qdot, .qaxis span").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON() as DOMRect));
      for (const b of boxes) {
        expect(b.left).toBeGreaterThanOrEqual(card.x - 0.5);
        expect(b.right).toBeLessThanOrEqual(card.x + card.width + 0.5);
      }
      const sizes = await chart.locator("p, h3, .qaxis span").evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
      for (const s of sizes) expect(s).toBeGreaterThanOrEqual(16);
      // The axis' labels do not run into each other.
      const ticks = await chart.locator(".qaxis span").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON() as DOMRect));
      for (let i = 1; i < ticks.length; i++) expect(ticks[i].left, "tick labels apart").toBeGreaterThanOrEqual(ticks[i - 1].right);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}
