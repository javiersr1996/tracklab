import { expect, type Request, test } from "@playwright/test";

interface Stats {
  tables: { table: string; sport: string; rows: number }[];
}

test("the home page starts playing on its own, light, with the figures of stats.json", async ({
  page,
}) => {
  const requests: Request[] = [];
  page.on("requestfinished", (r) => requests.push(r));
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("/");
  await page.waitForFunction(() => window.__replay?.state === "playing", null, {
    timeout: 2_000,
  });

  const stats = (await (await page.request.get("/data/stats.json")).json()) as Stats;
  for (const sport of ["basketball", "football"]) {
    const expected = stats.tables
      .filter((t) => t.table === "frames" && t.sport === sport)
      .reduce((sum, t) => sum + t.rows, 0);
    const shown = await page.locator(`[data-rows="${sport}"]`).textContent();
    console.log(`frames rows, ${sport}: page ${shown}, stats.json ${expected}`);
    expect(Number(shown?.replaceAll(",", ""))).toBe(expected);
  }

  await page.waitForLoadState("networkidle");
  let transferred = 0;
  for (const r of requests) {
    if (r.url().includes("/data/possessions/")) continue;
    const sizes = await r.sizes();
    transferred += sizes.responseBodySize + sizes.responseHeadersSize;
  }
  console.log(`home page: ${transferred} bytes transferred without the possessions`);
  expect(transferred).toBeLessThan(400_000);
  expect(errors).toEqual([]);
});

test("the selector switches sport and restarts the renderer", async ({ page }) => {
  await page.goto("/replay?p=bb_possessions_possession-114243-3-79.json");
  await page.waitForFunction(() => window.__replay?.sport === "basketball");
  await page.getByRole("button", { name: "Play" }).click();
  await page.waitForFunction(() => (window.__replay?.frameIndex ?? 0) > 5);

  await page.getByLabel("Sport").selectOption("football");
  await page.waitForFunction(() => window.__replay?.sport === "football");
  const after = await page.evaluate(() => window.__replay!);
  expect(after.frameIndex).toBe(0);
  expect(after.state).toBe("idle");
});
