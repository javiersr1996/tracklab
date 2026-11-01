import { expect, type Request, test } from "@playwright/test";

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
    expect(Number(text)).toBeCloseTo(expected.value, 6);
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
