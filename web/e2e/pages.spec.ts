import { expect, type Request, test } from "@playwright/test";

// Against a deployment (BASE_URL) there is no window.__replay: the checks read the page.
const EXPOSED = !process.env.BASE_URL;

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
  // Playing on its own: the button offers to pause.
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible({ timeout: 2_000 });
  // Replay.tsx sets window.__replay on its first animation frame, after the render that paints
  // the button: poll rather than read once.
  if (EXPOSED) await expect.poll(() => page.evaluate(() => window.__replay?.state)).toBe("playing");
  // The hero (P12): the replay's canvas is the first screen's background, with trails behind
  // the players; the headline sits over it, inside that first screen.
  const viewport = page.viewportSize()!;
  const canvas = await page.locator(".hero canvas").boundingBox();
  expect(canvas!.width).toBeGreaterThanOrEqual(viewport.width * 0.98);
  expect(canvas!.height).toBeGreaterThanOrEqual(viewport.height * 0.98);
  const title = await page.getByRole("heading", { level: 1 }).boundingBox();
  expect(title!.y + title!.height).toBeLessThanOrEqual(viewport.height);
  if (EXPOSED) await expect.poll(() => page.evaluate(() => window.__replay?.trail)).toBeGreaterThan(0);

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
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  const scrub = page.getByLabel("Scrub");
  await expect.poll(async () => Number(await scrub.inputValue())).toBeGreaterThan(
    Number(await scrub.getAttribute("min")),
  );

  await page.getByLabel("Sport").selectOption("football");
  await expect(page).toHaveURL(/p=fb_/);
  // A new renderer: idle, at its first frame.
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  expect(await scrub.inputValue()).toBe(await scrub.getAttribute("min"));
  if (EXPOSED) {
    const after = await page.evaluate(() => window.__replay!);
    expect([after.sport, after.state, after.frameIndex]).toEqual(["football", "idle", 0]);
    // The trails are the home's: /replay draws none.
    expect(after.trail).toBe(0);
  }
});

test("under prefers-reduced-motion the hero is a still frame, no trails, and offers Play", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible({ timeout: 2_000 });
  if (EXPOSED) {
    await expect.poll(() => page.evaluate(() => window.__replay?.state)).toBe("idle");
    expect(await page.evaluate(() => window.__replay!.trail)).toBe(0);
  }
  // The button still works: the replay is a choice, not denied.
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
});
