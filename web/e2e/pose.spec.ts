import { expect, type Page, type Request, test } from "@playwright/test";
import type { PoseClip } from "../lib/pose/types";

// `/pose` (task 56): the Body Pose sample in the viewer with its own projection. The viewer is
// driven from the console through `window.__pose` (state, t, frameIndex, yaw, tilt, skeletons,
// discs, player, probe, ticks), which exists in dev and test builds, not against a deployment.
// No capture is an assertion and nothing waits on a clock: every wait is on the viewer's state.
// Every figure is read back from the clip the page was served, never typed here.

const EXPOSED = !process.env.BASE_URL;
const CLIP = "/data/pose/1925299_phase406.json";
const WIDTHS = [390, 1440];

const resolve = (root: unknown, dotted: string): unknown =>
  dotted.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown>)?.[key], root);

async function clipOf(page: Page): Promise<PoseClip> {
  return (await (await page.request.get(CLIP)).json()) as PoseClip;
}

async function open(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/pose");
  await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "true");
  await expect(page.locator("figure.pose-viewer")).toBeVisible();
  return errors;
}

const pose = (page: Page) => page.evaluate(() => window.__pose!);
const posedIn = (clip: PoseClip, k: number) => clip.frames[k].p.filter((e) => e[4] !== null).length;

// What the pitch drew is what the clip holds in that frame: a skeleton for every player with a
// pose, a disc for every other, nothing carried over from another frame.
function expectDrawnIsTheClips(
  clip: PoseClip,
  k: number,
  drawn: { skeletons: number; discs: number },
  where: string,
) {
  const posed = posedIn(clip, k);
  expect(drawn.skeletons, `${where}: skeletons`).toBe(posed);
  expect(drawn.discs, `${where}: discs`).toBe(clip.frames[k].p.length - posed);
  expect(drawn.skeletons + drawn.discs, `${where}: every player`).toBe(32);
}

async function seek(page: Page, t: number) {
  await page.getByLabel("Scrub", { exact: true }).fill(String(t));
  await page.waitForFunction((m) => window.__pose?.t === m, t);
  return pose(page);
}

test("the viewer plays, pauses, seeks and turns from the console, and draws what the clip holds", async ({
  page,
}) => {
  test.skip(!EXPOSED, "window.__pose exists only in dev and test builds");
  const clip = await clipOf(page);
  const frames = clip.frames;
  const t0 = frames[0].t;
  const tEnd = frames[frames.length - 1].t;
  const frameMs = 1000 / clip.fps;
  const errors = await open(page);
  await page.waitForFunction(() => window.__pose?.state === "idle");
  const idle = await pose(page);
  expect([idle.frameIndex, idle.t, idle.player]).toEqual([0, t0, null]);
  expectDrawnIsTheClips(clip, 0, idle, "idle");

  // idle -> playing -> ended on the last frame at 2x, recording every frame the viewer visits.
  await page.getByLabel("Speed", { exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Play" }).click();
  await page.waitForFunction(() => window.__pose?.state === "playing");
  await expect(page.locator("figure.pose-viewer")).toHaveAttribute("data-state", /playing|ended/);
  const visited = await page.evaluate(
    () =>
      new Promise<Record<number, { skeletons: number; discs: number; frame: number }>>((done) => {
        const seen: Record<number, { skeletons: number; discs: number; frame: number }> = {};
        const look = () => {
          const p = window.__pose!;
          seen[p.frameIndex] = { skeletons: p.skeletons, discs: p.discs, frame: p.frame };
          if (p.state === "ended") done(seen);
          else requestAnimationFrame(look);
        };
        look();
      }),
  );
  const ended = await pose(page);
  expect([ended.state, ended.t, ended.frameIndex, ended.rate]).toEqual(["ended", tEnd, frames.length - 1, 2]);
  await expect(page.locator("figure.pose-viewer")).toHaveAttribute("data-state", "ended");
  const seen = Object.keys(visited).map(Number);
  console.log(`/pose: played at 2x, ${seen.length} of ${frames.length} frames visited and checked`);
  expect(seen.length).toBeGreaterThan(frames.length / 3);
  for (const k of seen) {
    expect(visited[k].frame).toBe(frames[k].f);
    expectDrawnIsTheClips(clip, k, visited[k], `frame ${frames[k].f} while playing`);
  }

  // Pause holds t while the animation keeps ticking.
  await page.getByRole("button", { name: "Play" }).click();
  await page.waitForFunction((start) => window.__pose?.state === "playing" && window.__pose.t > start, t0);
  await page.getByRole("button", { name: "Pause" }).click();
  await page.waitForFunction(() => window.__pose?.state === "paused");
  const held = await pose(page);
  await page.waitForFunction((n) => (window.__pose?.ticks ?? -1) >= n + 10, held.ticks, { timeout: 5_000 });
  const later = await pose(page);
  expect([later.state, later.t]).toEqual(["paused", held.t]);
  expect(later.ticks).toBeGreaterThanOrEqual(held.ticks + 10);

  // Seek to the middle (off a frame's own t): the frame shown is the one under it, within 40 ms.
  const middle = Math.round((t0 + tEnd) / 2) + 17;
  const atMiddle = await seek(page, middle);
  const shownT = frames[atMiddle.frameIndex].t;
  expect(middle - shownT).toBeGreaterThanOrEqual(0);
  expect(middle - shownT).toBeLessThan(frameMs);
  expect(atMiddle.frame).toBe(frames[atMiddle.frameIndex].f);
  expectDrawnIsTheClips(clip, atMiddle.frameIndex, atMiddle, "middle");

  // Yaw 180 turns u into -u, for one joint of one body, against the clip's own offsets.
  await page.getByLabel("Yaw", { exact: true }).fill("0");
  await page.waitForFunction(() => window.__pose?.yaw === 0);
  const p0 = (await pose(page)).probe!;
  const entry = frames[atMiddle.frameIndex].p.find((e) => e[0] === p0.i)!;
  const [dx, dy, dz] = entry[4]![0][clip.joints.indexOf(p0.joint)];
  expect(p0.u).toBeCloseTo(dx / 100, 6);
  await page.getByLabel("Yaw", { exact: true }).fill("180");
  await page.waitForFunction(() => window.__pose?.yaw === 180);
  const p180 = (await pose(page)).probe!;
  expect(p180.i).toBe(p0.i);
  expect(p180.u).toBeCloseTo(-p0.u, 6);

  // Tilt: straight down, v ignores dz; level, v is dz, so a joint above the origin goes up.
  await page.getByLabel("Yaw", { exact: true }).fill("0");
  await page.getByLabel("Tilt", { exact: true }).fill("0");
  await page.waitForFunction(() => window.__pose?.yaw === 0 && window.__pose.tilt === 0);
  const flat = (await pose(page)).probe!;
  expect(flat.v).toBeCloseTo(dy / 100, 6);
  await page.getByLabel("Tilt", { exact: true }).fill("90");
  await page.waitForFunction(() => window.__pose?.tilt === 90);
  const level = (await pose(page)).probe!;
  expect(dz).toBeGreaterThan(0);
  expect(level.v).toBeCloseTo(dz / 100, 6);
  expect(level.v).toBeGreaterThan(flat.v);
  console.log(`/pose probe ${p0.joint} of player ${p0.i}: u ${p0.u} -> ${p180.u} at yaw 180; v ${flat.v} -> ${level.v} at tilt 90`);

  // A player who loses the pose from one frame to the next: followed, he is a skeleton, then a
  // disc, on his own panel and on the pitch, and the pitch's skeletons go down with the clip's.
  let k = -1;
  let lost = -1;
  for (let j = 0; j + 1 < frames.length && k < 0; j++) {
    const next = frames[j + 1].p.find((e) => e[4] === null && frames[j].p.find((p) => p[0] === e[0])?.[4]);
    if (next && posedIn(clip, j + 1) < posedIn(clip, j)) [k, lost] = [j, next[0]];
  }
  expect(k, "a frame of the sample where a player loses the pose").toBeGreaterThanOrEqual(0);
  const follow = page.locator(".pose-follow");
  await seek(page, frames[k + 1].t);
  await page.getByLabel("Player", { exact: true }).selectOption(String(lost));
  await page.waitForFunction((i) => window.__pose?.player?.i === i, lost);
  let s = await pose(page);
  expect(s.player).toEqual({ i: lost, shows: "disc" });
  await expect(follow).toHaveAttribute("data-follow", "disc");
  s = await seek(page, frames[k].t);
  expect(s.player).toEqual({ i: lost, shows: "skeleton" });
  expect(s.probe?.i).toBe(lost);
  await expect(follow).toHaveAttribute("data-follow", "skeleton");
  expectDrawnIsTheClips(clip, k, s, `frame ${frames[k].f}`);
  const before = s.skeletons;
  s = await seek(page, frames[k + 1].t);
  expect(s.player).toEqual({ i: lost, shows: "disc" });
  await expect(follow).toHaveAttribute("data-follow", "disc");
  expectDrawnIsTheClips(clip, k + 1, s, `frame ${frames[k + 1].f}`);
  expect(s.skeletons).toBeLessThan(before);
  console.log(`/pose: player ${lost} loses the pose at frame ${frames[k + 1].f}; skeletons ${before} -> ${s.skeletons}`);

  // A spread of frames by seeking, each drawn as the clip holds it.
  for (let j = 0; j < frames.length; j += 25) {
    const at = await seek(page, frames[j].t);
    expectDrawnIsTheClips(clip, j, at, `seek to frame ${frames[j].f}`);
  }
  expect(errors).toEqual([]);
});

test("every figure on /pose is the clip's, and its three limits sit next to the viewer", async ({ page }) => {
  const clip = await clipOf(page);
  const errors = await open(page);

  await expect(page.locator("h1")).toHaveText(`${clip.joints.length} joints`);
  const shown = await page
    .locator("[data-fig]")
    .evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig"), (e.textContent ?? "").trim()]));
  const wrong: string[] = [];
  for (const [p, text] of shown) {
    const value = resolve(clip, p ?? "");
    if (value === undefined) wrong.push(`${p}: not in the clip`);
    else if (text !== String(value)) wrong.push(`${p}: page "${text}", clip ${String(value)}`);
  }
  expect(wrong).toEqual([]);
  const roots = new Set(shown.map(([p]) => (p ?? "").split(".")[0]));
  for (const root of ["joints", "match_id", "period", "frame_lo", "frame_hi", "fps", "limits", "coverage"]) {
    expect(roots, `no figure of ${root}`).toContain(root);
  }
  for (const p of ["p90_mae_cm.median", "p90_mae_cm.p90", "with_joints", "player_frames", "skeletons_per_frame.max"]) {
    expect(shown.map(([q]) => q), p).toContain(`coverage.${p}`);
  }
  console.log(`/pose: ${shown.length} figures checked against the clip`);

  // The three limits, word for word from the clip, with their README lines.
  const limits = page.locator("aside.pose-limits [data-limit]");
  await expect(limits).toHaveCount(clip.limits.length);
  for (const [j, limit] of clip.limits.entries()) {
    await expect(limits.nth(j)).toHaveAttribute("data-limit", limit.id);
    await expect(limits.nth(j).locator("blockquote")).toHaveText(limit.text);
    await expect(limits.nth(j).locator("cite")).toHaveText(limit.readme);
  }

  // No figure typed into the prose, and nothing that reads z as a height.
  const prose = await page.evaluate(() => {
    const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
    main.querySelectorAll("[data-fig], code, figure.pose-viewer").forEach((e) => e.remove());
    return main.textContent ?? "";
  });
  expect(prose.match(/\d+/g), "a figure typed into the prose").toBeNull();
  expect(prose).not.toMatch(/\b(height|heights|tall|elevation|altitude|jump|jumps)\b/i);
  expect(errors).toEqual([]);
});

for (const width of WIDTHS) {
  test(`/pose at ${width} px: no sideways scroll, no overlaps, text of 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const clip = await clipOf(page);
    await open(page);
    // Follow a player, so his own panel is part of the layout.
    await page.getByLabel("Player", { exact: true }).selectOption(String(clip.frames[0].p.find((e) => e[4] !== null)![0]));
    await expect(page.locator(".pose-follow canvas")).toBeVisible();

    const fit = await page.evaluate(() => ({
      page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      viewer: (() => {
        const f = document.querySelector("figure.pose-viewer")!;
        return f.scrollWidth - f.clientWidth;
      })(),
      canvases: Array.from(document.querySelectorAll("main canvas")).map((c) => {
        const r = c.getBoundingClientRect();
        return { right: r.right, width: r.width };
      }),
      window: window.innerWidth,
    }));
    expect(fit.page, "page wider than the window by").toBeLessThanOrEqual(0);
    expect(fit.viewer, "viewer wider than its box by").toBeLessThanOrEqual(0);
    expect(fit.canvases).toHaveLength(2);
    for (const c of fit.canvases) expect(c.right).toBeLessThanOrEqual(fit.window + 0.5);

    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .filter((el) =>
          Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""),
        )
        .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
        .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}: ${(el.textContent ?? "").slice(0, 30)}`),
    );
    expect(small, "text under 16 px").toEqual([]);

    // Top-level blocks stack; the viewer and the limits sit side by side or stacked, never
    // crossing; the controls stay inside the viewer.
    const boxes = await page.evaluate(() => {
      const rect = (e: Element) => {
        const r = e.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top + window.scrollY, bottom: r.bottom + window.scrollY };
      };
      const viewer = document.querySelector("figure.pose-viewer")!;
      return {
        blocks: Array.from(document.querySelector("main")!.children).map((e) => ({ tag: e.tagName.toLowerCase(), ...rect(e) })),
        viewer: rect(viewer),
        limits: rect(document.querySelector("aside.pose-limits")!),
        inner: Array.from(viewer.children).map(rect),
      };
    });
    for (let i = 1; i < boxes.blocks.length; i++) {
      expect(boxes.blocks[i].top, `${boxes.blocks[i].tag} #${i} overlaps the block above`).toBeGreaterThanOrEqual(
        boxes.blocks[i - 1].bottom - 1,
      );
    }
    const [a, b] = [boxes.viewer, boxes.limits];
    const apart = a.right <= b.left + 0.5 || a.bottom <= b.top + 0.5;
    expect(apart, "the viewer and the limits overlap").toBe(true);
    for (let i = 1; i < boxes.inner.length; i++) {
      expect(boxes.inner[i].top, `viewer row ${i}`).toBeGreaterThanOrEqual(boxes.inner[i - 1].bottom - 1);
      expect(boxes.inner[i].right).toBeLessThanOrEqual(a.right + 0.5);
    }
    console.log(`/pose at ${width} px: limits ${a.right <= b.left + 0.5 ? "beside" : "below"} the viewer`);
  });
}

test("the bytes /pose transfers, printed with no verdict, the clip apart", async ({ page }) => {
  const requests: Request[] = [];
  page.on("requestfinished", (r) => requests.push(r));
  await open(page);
  await page.waitForLoadState("networkidle");
  let rest = 0;
  let clip = 0;
  let script = 0;
  for (const r of requests) {
    const sizes = await r.sizes();
    const bytes = sizes.responseBodySize + sizes.responseHeadersSize;
    if (r.url().includes(CLIP)) clip += bytes;
    else rest += bytes;
    if (r.resourceType() === "script") script += bytes;
  }
  console.log(`/pose: ${rest} bytes transferred without the clip (${script} of them scripts); the clip ${clip} bytes`);
  expect(clip).toBeGreaterThan(0);
});

test("the home page links to /pose", async ({ page }) => {
  await page.goto("/");
  const link = page.getByRole("link", { name: "Body pose" });
  await expect(link).toHaveAttribute("href", "/pose");
  await link.click();
  await expect(page).toHaveURL(/\/pose$/);
  await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "true");
});
