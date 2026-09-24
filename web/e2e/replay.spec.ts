import { expect, type Page, test } from "@playwright/test";
import type { Possession } from "../lib/replay/types";

// One possession per sport through the same component, both with attack_sign = -1
// so the normalize switch has a sign to flip.
const FILES = ["bb_possessions_possession-114243-3-79.json", "fb_possession_1899585_123.json"];

const replay = (page: Page) => page.evaluate(() => window.__replay!);

for (const file of FILES) {
  test(`plays ${file} from the console`, async ({ page }, info) => {
    const possession = (await (
      await page.request.get(`/data/possessions/${file}`)
    ).json()) as Possession;
    const frames = possession.frames;
    const t0 = frames[0].t;
    const tEnd = frames[frames.length - 1].t;
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto(`/replay?p=${file}`);
    await page.waitForFunction(() => window.__replay?.state === "idle");
    expect((await replay(page)).sport).toBe(possession.sport);

    // idle -> playing -> ended, on the last frame. Rate 2 halves the wait.
    await page.getByLabel("Speed").selectOption("2");
    await page.getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => window.__replay?.state === "playing");
    await page.waitForFunction(() => window.__replay?.state === "ended", null, {
      timeout: 30_000,
    });
    const ended = await replay(page);
    expect(ended.rate).toBe(2);
    expect(ended.t).toBe(tEnd);
    expect(ended.frameIndex).toBe(frames.length - 1);
    await page.screenshot({ path: info.outputPath("ended.png") });

    // Pause holds t for 500 ms.
    await page.getByRole("button", { name: "Play" }).click();
    await page.waitForFunction(() => (window.__replay?.t ?? 0) > 0 && window.__replay?.state === "playing");
    await page.getByRole("button", { name: "Pause" }).click();
    const paused = (await replay(page)).t;
    await page.waitForTimeout(500);
    expect((await replay(page)).state).toBe("paused");
    expect((await replay(page)).t).toBe(paused);

    // Seek to the middle, within one frame.
    const middle = Math.round((t0 + tEnd) / 2);
    await page.getByLabel("Scrub").fill(String(middle));
    await page.waitForFunction((m) => window.__replay?.t === m, middle);
    const frameMs = 1000 / possession.sample_rate_hz;
    expect(Math.abs((await replay(page)).t - middle)).toBeLessThanOrEqual(frameMs);

    // Normalize: attack_sign = -1 turns the venue frame 180 degrees.
    const before = (await replay(page)).entities[0];
    await page.getByLabel("normalize attack →").check();
    await page.waitForFunction(() => window.__replay?.normalized === true);
    const after = (await replay(page)).entities.find((e) => e.i === before.i)!;
    console.log(`${file}: entity ${before.i} x ${before.x.toFixed(2)} -> ${after.x.toFixed(2)}`);
    expect(possession.attack_sign).toBe(-1);
    expect(after.x).toBeCloseTo(-before.x, 9);
    await page.screenshot({ path: info.outputPath("normalized.png") });

    expect(errors).toEqual([]);
  });
}
