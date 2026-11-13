import { expect, type Request, test } from "@playwright/test";
import { formatBytes } from "../lib/format";

// Against a deployment (BASE_URL) there is no window.__replay: the checks read the page.
const EXPOSED = !process.env.BASE_URL;

interface Stats {
  tables: { table: string; sport: string; rows: number }[];
}

interface Platform {
  title: string;
  layers: { layer: string; bytes: number }[];
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

  // The figures (task 106) count up once they scroll into view, then land on the JSON's numbers:
  // two sports from stats.json; the title from platform.json, and its six layers' bytes, which P20
  // moved from counters here onto the architecture (task 173).
  await page.locator(".figures").scrollIntoViewIfNeeded();
  const counters = page.locator("[data-count]");
  await expect(counters).toHaveCount(2);
  await expect.poll(() => counters.evaluateAll((els) => els.map((e) => e.getAttribute("data-count")))).toContain(
    "counting",
  );
  // Landed within 2 s of coming into view (P20, task 174: the /engineering counters' rule).
  await expect.poll(() => counters.evaluateAll((els) => els.every((e) => e.getAttribute("data-count") === "done")), {
    timeout: 2_000,
  }).toBe(true);
  const stats = (await (await page.request.get("/data/stats.json")).json()) as Stats;
  // The server's HTML already carries each number, so no reader without JS sees a 0.
  const html = await (await page.request.get("/")).text();
  for (const sport of ["basketball", "football"]) {
    const expected = stats.tables
      .filter((t) => t.table === "frames" && t.sport === sport)
      .reduce((sum, t) => sum + t.rows, 0);
    const shown = await page.locator(`[data-rows="${sport}"]`).textContent();
    console.log(`frames rows, ${sport}: page ${shown}, stats.json ${expected}`);
    expect(Number(shown?.replaceAll(",", ""))).toBe(expected);
    const served = html.match(new RegExp(`data-rows="${sport}"[^>]*><span[^>]*>([^<]*)<`))?.[1];
    expect(served, `${sport} in the server's HTML`).toBe(expected.toLocaleString("en-US"));
  }
  const platform = (await (await page.request.get("/data/platform.json")).json()) as Platform;
  await expect(page.locator("[data-platform-title]")).toHaveText(platform.title);
  for (const layer of platform.layers) {
    await expect(page.locator(`[data-layer-bytes="${layer.layer}"]`)).toHaveText(formatBytes(layer.bytes));
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
  await page.goto("/tracking/replay?p=bb_possessions_possession-114243-3-79.json");
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
    // The hero's trails, drawn by the same renderer (P21; until then /tracking/replay drew none).
    expect(after.trail).toBeGreaterThan(0);
  }
});

test("/tracking/replay draws no trail under prefers-reduced-motion, and still plays", async ({ page }) => {
  test.skip(!EXPOSED, "needs window.__replay");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/tracking/replay?p=fb_possession_1899585_123.json");
  await expect.poll(() => page.evaluate(() => window.__replay?.state)).toBe("idle");
  await page.getByRole("button", { name: "Play" }).click();
  await expect.poll(() => page.evaluate(() => window.__replay?.state)).toBe("playing");
  expect(await page.evaluate(() => window.__replay!.trail)).toBe(0);
});

interface ContextFile {
  sport: string;
  match: { home: string; away: string; kickoff_utc: string };
  sample_rate_hz: number;
  entities: { kind: string }[];
  frames: unknown[];
  surface: { length_m: number; width_m: number };
}

// The panel beside the player (P21): the possession file's facts, beside the canvas from 1000 px
// and filling the row's right side, under it on a phone.
for (const width of [390, 1440]) {
  test(`/tracking/replay at ${width} px: the context panel prints the file's facts, beside or under the player`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const file = "bb_possessions_possession-114243-3-79.json";
    const p = (await (await page.request.get(`/data/possessions/${file}`)).json()) as ContextFile;
    await page.goto(`/tracking/replay?p=${file}`);
    const panel = page.locator("[data-replay-context]");
    await expect(panel).toBeVisible();
    const fact = (k: string) => panel.locator(`[data-context="${k}"]`);
    await expect(fact("sport")).toHaveText(p.sport);
    await expect(fact("match")).toHaveText(`${p.match.home} v ${p.match.away}, ${p.match.kickoff_utc.slice(0, 10)}`);
    await expect(fact("rate")).toHaveText(`${p.sample_rate_hz} times a second, ${p.frames.length} frames`);
    await expect(fact("players")).toHaveText(`${p.entities.filter((e) => e.kind === "player").length} players and the ball`);
    await expect(fact("surface")).toHaveText(`${p.surface.length_m} by ${p.surface.width_m} m`);
    await expect(panel).toContainText("One Canvas renderer draws both sports from the same frames schema");

    const canvas = (await page.locator("figure.replay canvas").boundingBox())!;
    const box = (await panel.boundingBox())!;
    if (width >= 1000) {
      expect(box.x, "the panel starts right of the canvas").toBeGreaterThanOrEqual(canvas.x + canvas.width);
      const main = (await page.locator(".replay-stage").boundingBox())!;
      expect(box.x + box.width, "the panel reaches the row's right edge").toBeGreaterThan(main.x + main.width - 2);
    } else {
      expect(box.y, "the panel sits under the player").toBeGreaterThanOrEqual(canvas.y + canvas.height);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}

// Since P23 the first action opens the lessons, the second the replay.
test("the hero's actions: Browse the lessons opens /learn, Open replay follows the possession playing", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible({ timeout: 2_000 });
  const lessons = page.getByRole("link", { name: "Browse the lessons" });
  const open = page.getByRole("link", { name: "Open replay" });
  // Both inside the first screen, 44 px tall, real links.
  for (const link of [lessons, open]) {
    const box = (await link.boundingBox())!;
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  }
  await expect(lessons).toHaveAttribute("href", "/learn");
  await expect(lessons).toHaveClass(/hero-action-primary/);
  const href = (await open.getAttribute("href"))!;
  expect(href).toMatch(/^\/tracking\/replay\?p=(bb|fb)_/);
  if (EXPOSED) {
    const sport = await page.evaluate(() => window.__replay!.sport);
    expect(href).toContain(sport === "basketball" ? "p=bb_" : "p=fb_");
  }
  // Keyboard: focus and Enter open that very possession on /tracking/replay, idle, with the
  // hero's trails (P21).
  await open.focus();
  await expect(open).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL((url) => url.pathname + url.search === href);
  await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
  if (EXPOSED) {
    await expect.poll(() => page.evaluate(() => window.__replay?.state)).toBe("idle");
    await expect.poll(() => page.evaluate(() => window.__replay!.trail)).toBeGreaterThan(0);
  }
});

interface PossessionFile {
  entities: { i: number; kind: string; jersey: string | null }[];
  frames: { t: number; o: [number, number, number, number | null, 0 | 1][] }[];
}

// Where entity `i` is at `t`: linear between the two samples around it, as the engine does.
function positionAt(frames: PossessionFile["frames"], i: number, t: number): [number, number] | null {
  let k = 0;
  while (k + 1 < frames.length && frames[k + 1].t <= t) k++;
  const a = frames[k];
  const b = frames[Math.min(k + 1, frames.length - 1)];
  const oa = a.o.find((o) => o[0] === i);
  const ob = b.o.find((o) => o[0] === i);
  if (!oa || !ob) return null;
  const alpha = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t);
  return [oa[1] + (ob[1] - oa[1]) * alpha, oa[2] + (ob[2] - oa[2]) * alpha];
}

test("hovering a player in the hero shows his number and his speed from the frames; a click opens the possession", async ({
  page,
}) => {
  test.skip(!EXPOSED, "needs window.__replay for the marks' positions");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible({ timeout: 2_000 });
  // Past the 400 ms speed window, then frozen, so the readout and this test see the same t.
  await page.waitForTimeout(1_200);
  await page.getByRole("button", { name: "Pause" }).click();
  await expect.poll(() => page.evaluate(() => window.__replay?.state)).toBe("paused");
  const state = await page.evaluate(() => window.__replay!);
  const href = (await page.getByRole("link", { name: "Open replay" }).getAttribute("href"))!;
  const file = href.split("p=")[1];
  const possession = (await (await page.request.get(`/data/possessions/${file}`)).json()) as PossessionFile;
  const players = new Map(possession.entities.filter((e) => e.kind === "player").map((e) => [e.i, e]));
  const canvas = (await page.locator(".hero canvas").boundingBox())!;
  // A player present at both ends of the speed window whose mark the pointer can reach: not
  // under the header, the controls or the copy (the canvas is what sits at that point).
  const candidates = state.entities.filter(
    (e) => players.has(e.i) && e.px !== undefined && positionAt(possession.frames, e.i, state.t - 400) !== null,
  );
  const reachable = await page.evaluate(
    ({ list, box }) =>
      list.map((e) => {
        const hit = document.elementFromPoint(box.x + e.px!, box.y + e.py!);
        return hit?.tagName === "CANVAS";
      }),
    { list: candidates, box: canvas },
  );
  const target = candidates.find((_, k) => reachable[k]);
  expect(target, "a player whose mark the pointer can reach").toBeTruthy();
  await page.mouse.move(canvas.x + target!.px!, canvas.y + target!.py!);
  const readout = page.locator(".replay-hero-player");
  await expect(readout).toBeVisible();
  await expect(readout).toContainText(`#${players.get(target!.i)!.jersey}`);
  const [x0, y0] = positionAt(possession.frames, target!.i, state.t - 400)!;
  const [x1, y1] = positionAt(possession.frames, target!.i, state.t)!;
  const expected = Math.hypot(x1 - x0, y1 - y0) / 0.4;
  // The loop writes the speed on the next animation frame after the readout appears.
  const speed = readout.locator("output");
  await expect(speed).toHaveText(/^\d+\.\d m\/s$/);
  const shown = await speed.textContent();
  console.log(`speed of #${players.get(target!.i)!.jersey}: readout ${shown}, frames ${expected.toFixed(3)} m/s`);
  // One decimal shown: within half a unit of the last place, plus a hair.
  expect(Math.abs(Number(shown!.replace(" m/s", "")) - expected)).toBeLessThanOrEqual(0.06);
  // A right click on the picked player opens nothing; a click does.
  await page.mouse.click(canvas.x + target!.px!, canvas.y + target!.py!, { button: "right" });
  await page.waitForTimeout(300);
  await expect(page).toHaveURL(/\/$/);
  await page.mouse.click(canvas.x + target!.px!, canvas.y + target!.py!);
  await expect(page).toHaveURL((url) => url.pathname + url.search === href);
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
  // The figures never count: they are the final numbers from the first paint.
  await page.locator(".figures").scrollIntoViewIfNeeded();
  const counters = page.locator("[data-count]");
  await expect(counters).toHaveCount(2);
  expect(await counters.evaluateAll((els) => els.map((e) => e.getAttribute("data-count")))).toEqual(
    Array(2).fill("still"),
  );
  const stats = (await (await page.request.get("/data/stats.json")).json()) as Stats;
  const expected = stats.tables
    .filter((t) => t.table === "frames" && t.sport === "football")
    .reduce((sum, t) => sum + t.rows, 0);
  await expect(page.locator('[data-rows="football"]')).toHaveText(expected.toLocaleString("en-US"));
  // The cards' sketches stand still at a resting frame: the replay's marks sit on its court, not
  // at the origin, and the pose's limbs are swung, not folded onto the torso.
  const court = (await page.locator(".pv-replay").boundingBox())!;
  for (const mark of await page.locator(".pv-replay .pv-mark").all()) {
    const box = (await mark.boundingBox())!;
    expect(box.x, "mark inside the court, not at the origin").toBeGreaterThan(court.x + court.width * 0.1);
    expect(box.y).toBeGreaterThan(court.y + court.height * 0.1);
  }
  const limbs = await page.locator(".pv-pose .pv-arm, .pv-pose .pv-leg").evaluateAll((els) =>
    els.map((e) => e.getBoundingClientRect().width),
  );
  expect(limbs.length).toBe(4);
  for (const width of limbs) expect(width, "a swung limb is wider than a line").toBeGreaterThan(2);
});

// P13: a phone must not scroll sideways on the pages the neon theme touched.
test.describe("no horizontal scroll at 390 px", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  for (const path of ["/tracking", "/tracking/replay", "/engineering/quality", "/engineering", "/engineering/bulletin", "/engineering/history", "/warehouse", "/warehouse/scouting", "/warehouse/positions", "/tracking/occupancy", "/sql", "/sql/select"]) {
    test(path, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("load");
      const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(over).toBeLessThanOrEqual(0);
    });
  }
});
