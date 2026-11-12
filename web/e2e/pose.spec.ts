import { readFileSync } from "node:fs";
import path from "node:path";
import { expect as baseExpect, type Page, type Request, test } from "@playwright/test";
import type { PoseClip, PoseSummary } from "../lib/pose/types";

// Eleven workers share one server and the clip is megabytes: the waits are on the page's own
// state, with room for a loaded machine, and nothing waits on a clock.
const expect = baseExpect.configure({ timeout: 20_000 });

// `/tracking/pose` (task 56): the Body Pose sample in the viewer with its own projection. The viewer is
// driven from the console through `window.__pose` (state, t, frameIndex, yaw, tilt, skeletons,
// discs, player, probe, ticks), which exists in dev and test builds, not against a deployment.
// No capture is an assertion and nothing waits on a clock: every wait is on the viewer's state.
// Every figure is read back from the clip the page was served, never typed here.

const EXPOSED = !process.env.BASE_URL;
const CLIP = "/data/pose/1925299_phase406.json";
const SUMMARY = "/data/pose.json";
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
  await page.goto("/tracking/pose");
  await page.getByRole("button", { name: /Load the clip/ }).click();
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
  console.log(`/tracking/pose: played at 2x, ${seen.length} of ${frames.length} frames visited and checked`);
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
  console.log(`/tracking/pose probe ${p0.joint} of player ${p0.i}: u ${p0.u} -> ${p180.u} at yaw 180; v ${flat.v} -> ${level.v} at tilt 90`);

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
  console.log(`/tracking/pose: player ${lost} loses the pose at frame ${frames[k + 1].f}; skeletons ${before} -> ${s.skeletons}`);

  // A spread of frames by seeking, each drawn as the clip holds it.
  for (let j = 0; j < frames.length; j += 25) {
    const at = await seek(page, frames[j].t);
    expectDrawnIsTheClips(clip, j, at, `seek to frame ${frames[j].f}`);
  }
  expect(errors).toEqual([]);
});

// Every `data-fig` element holds the value at its path in `pose.json`, and every `data-clip-fig`
// the value at its path in the clip on show: the text and the number agree with the file.
async function expectFigures(page: Page, summary: PoseSummary, clip: PoseClip) {
  const shown = await page
    .locator("[data-fig], [data-clip-fig]")
    .evaluateAll((els) =>
      els.map((e) => [e.getAttribute("data-fig"), e.getAttribute("data-clip-fig"), (e.textContent ?? "").trim()]),
    );
  const wrong: string[] = [];
  for (const [fig, clipFig, text] of shown) {
    const [root, p] = fig !== null ? [summary, fig] : [clip, clipFig ?? ""];
    const value = resolve(root, p);
    if (value === undefined) wrong.push(`${p}: not in the file`);
    else if (text !== String(value)) wrong.push(`${p}: page "${text}", file ${String(value)}`);
    else if (typeof value === "number" && Number(text) !== value) wrong.push(`${p}: ${text}`);
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  return shown.map(([fig, clipFig]) => fig ?? clipFig ?? "");
}

// The prose is what is left once the figures, the code, the viewer, the clip selector and the
// tables are taken out: no digit is typed in it.
const proseOf = (page: Page) =>
  page.evaluate(() => {
    const main = document.querySelector("main")!.cloneNode(true) as HTMLElement;
    main
      .querySelectorAll("[data-fig], [data-clip-fig], code, figure.pose-viewer, .pose-clips, table")
      .forEach((e) => e.remove());
    return main.textContent ?? "";
  });

const FORBIDDEN = /\b(faster|better|efficient|asymmetric|asymmetry|fatigue|injury|injuries)\b/i;
const HEIGHT = /\b(height|heights|tall|elevation|altitude|jump|jumps)\b/i;

async function publishedSummary(page: Page): Promise<PoseSummary> {
  return (await (await page.request.get(SUMMARY)).json()) as PoseSummary;
}

const fixture = (name: "alive" | "unreplicated" | "dead" | "dead-m1" | "dead-m2" | "dead-noise"): PoseSummary =>
  JSON.parse(readFileSync(path.join(process.cwd(), "e2e", "fixtures", `pose.${name}.json`), "utf-8"));

// Hands the page `summary` as `/data/pose.json`. A file dead at M4 names stretches no build has
// published, so the hook clips stand in for them, without their windows.
async function openWith(page: Page, summary: PoseSummary) {
  const published = await publishedSummary(page);
  const clips = new Map<string, PoseClip>();
  for (const record of summary.clips) {
    const real = published.clips.find((c) => c.match_id === record.match_id)!;
    const clip = (await (await page.request.get(`/data/${real.file}`)).json()) as PoseClip;
    clips.set(
      record.file,
      record.kind === real.kind ? clip : { ...clip, selection: { kind: record.kind, rule: record.selection.rule }, windows: [] },
    );
  }
  await page.route("**/data/pose.json", (route) => route.fulfill({ json: summary }));
  for (const [file, clip] of clips) await page.route(`**/data/${file}`, (route) => route.fulfill({ json: clip }));
  return { errors: await open(page), clips };
}

test("every figure on /tracking/pose is a file's, its three limits sit next to the viewer, and the state shows", async ({
  page,
}) => {
  const clip = await clipOf(page);
  const summary = await publishedSummary(page);
  const errors = await open(page);

  await expect(page.locator("h1")).toHaveText(`${clip.joints.length} joints`);
  const paths = await expectFigures(page, summary, clip);
  for (const root of ["limits", "protocol", "coverage", "tables", "verdict"]) {
    expect(paths.filter((q) => q.startsWith(`${root}.`)).length, `no figure of ${root}`).toBeGreaterThan(0);
  }
  for (const p of ["joints.length", "match_id", "period", "frame_lo", "frame_hi", "fps", "coverage.with_joints"]) {
    expect(paths, p).toContain(p);
  }
  console.log(`/tracking/pose: ${paths.length} figures checked against pose.json and the clip`);

  // The state of the project, from the file.
  const status = page.locator("[data-section=status]");
  await expect(status).toHaveAttribute("data-status", summary.status);
  await expect(status).toHaveAttribute("data-dead-at", summary.dead_at ?? "");

  // The three limits, word for word from the file, with their README lines, beside the viewer.
  const limits = page.locator("aside.pose-limits [data-limit]");
  await expect(limits).toHaveCount(summary.limits.length);
  for (const [j, limit] of summary.limits.entries()) {
    await expect(limits.nth(j)).toHaveAttribute("data-limit", limit.id);
    await expect(limits.nth(j).locator("blockquote")).toHaveText(limit.text);
    await expect(limits.nth(j).locator("cite")).toHaveText(limit.readme);
  }

  // No figure typed into the prose, nothing that reads z as a height (the scope line says there
  // is none), none of the forbidden words.
  const prose = await proseOf(page);
  expect(prose.match(/\d+/g), "a figure typed into the prose").toBeNull();
  const scope = (await page.locator("[data-scope]").first().textContent()) ?? "";
  expect(prose.replace(scope, "")).not.toMatch(HEIGHT);
  expect(await page.locator("main").innerHTML()).not.toMatch(FORBIDDEN);
  expect(errors).toEqual([]);
});

test("the tables carry a denominator in every row, the sd beside each value, and keep team and shirt order", async ({
  page,
}) => {
  const summary = await publishedSummary(page);
  const tables = summary.tables!;
  const c = (name: string) => tables.columns.indexOf(name);
  await open(page);
  expect(await page.locator("table th button, table th [role=button], table th a").count(), "a sort control").toBe(0);
  for (const match of Object.keys(tables.matches)) {
    const rows = tables.matches[match];
    const wanted = rows.flatMap((row, i) => (row[c("period")] === "all" ? [i] : []));
    const table = page.locator(`table[data-table=players][data-match="${match}"]`);
    await expect(table.locator("tbody tr")).toHaveCount(wanted.length);
    const seen = await table.locator("tbody tr").evaluateAll((trs) =>
      trs.map((tr) => ({
        row: tr.getAttribute("data-row"),
        figs: Array.from(tr.querySelectorAll("[data-fig]")).map((e) => e.getAttribute("data-fig")),
      })),
    );
    expect(seen.map((r) => r.row)).toEqual(wanted.map((i) => `${match}.${i}`));
    for (const [k, i] of wanted.entries()) {
      const base = `tables.matches.${match}.${i}`;
      // The denominator: windows and the windows finite in s, in the row.
      expect(seen[k].figs, `row ${base}: its denominator`).toEqual(
        expect.arrayContaining([`${base}.${c("windows")}`, `${base}.${c("finite_s")}`]),
      );
      // Every value shown with a propagated sd has the sd's figure next to it.
      for (const [v, sd] of [
        ["cad_s_p50_hz", "cad_s_sd_hz"],
        ["step_length_p50_m", "step_length_sd_m"],
        ["ankle_separation_p50_m", "ankle_separation_sd_m"],
        ["separation_over_step", "separation_over_step_sd"],
      ]) {
        const row = rows[i];
        if (row[c(v)] === null) continue;
        expect(seen[k].figs).toContain(`${base}.${c(v)}`);
        if (row[c(sd)] !== null) expect(seen[k].figs, `${base}: ${v} without its sd`).toContain(`${base}.${c(sd)}`);
      }
    }
    // By team, then shirt number: never by a metric.
    const order = wanted.map((i) => [rows[i][c("team_id")], rows[i][c("number")]] as [number, number]);
    expect(order).toEqual([...order].sort((a, b) => a[0] - b[0] || a[1] - b[1]));
  }
  // M3 beside the cadence, without an error, and saying it; its tables name their match and
  // carry the same denominator in every row.
  await expect(page.locator("[data-section=m3]")).toContainText("no propagated error");
  for (const match of Object.keys(tables.matches)) {
    const rows = tables.matches[match];
    const wanted = rows.flatMap((row, i) =>
      row[c("period")] === "all" && row[c("band")] === "high" && row[c("m3_abs_diff_p50_hz")] !== null ? [i] : [],
    );
    const m3 = page.locator(`table[data-table=m3][data-match="${match}"]`);
    const id = match === String(summary.protocol.calibration) ? "calibration" : "confirmation";
    await expect(m3.locator("caption [data-fig]")).toHaveAttribute("data-fig", `protocol.${id}`);
    await expect(m3.locator("caption")).toContainText(match);
    const seen = await m3.locator("tbody tr").evaluateAll((trs) =>
      trs.map((tr) => Array.from(tr.querySelectorAll("[data-fig]")).map((e) => e.getAttribute("data-fig"))),
    );
    expect(seen).toHaveLength(wanted.length);
    for (const [k, i] of wanted.entries()) {
      const base = `tables.matches.${match}.${i}`;
      expect(seen[k], `m3 row ${base}: its denominator`).toEqual(
        expect.arrayContaining([`${base}.${c("windows")}`, `${base}.${c("finite_s")}`, `${base}.${c("m3_abs_diff_p50_hz")}`]),
      );
    }
  }
});

test("the hook clip paints s(t) under the viewer, and the playhead follows the frame shown", async ({ page }) => {
  test.skip(!EXPOSED, "window.__pose exists only in dev and test builds");
  const summary = await publishedSummary(page);
  expect(summary.status).not.toBe("dead");
  await open(page);
  expect(await page.locator("[data-signal]").count(), "the sample has no window").toBe(0);
  for (const record of summary.clips) {
    const clip = (await (await page.request.get(`/data/${record.file}`)).json()) as PoseClip;
    await page.getByLabel("Clip", { exact: true }).selectOption(record.file);
    await page.waitForFunction((f) => window.__pose?.state === "idle" && window.__pose.frame === f, clip.frames[0].f);
    expect(clip.windows!.length).toBeGreaterThan(0);
    await expectFigures(page, summary, clip);
    // One polyline per window, one point per frame of the window, from the clip's own s_mm.
    const lines = page.locator("[data-signal] polyline");
    await expect(lines).toHaveCount(clip.windows!.length);
    for (const [k, w] of clip.windows!.entries()) {
      const n = await lines.nth(k).evaluate((el) => (el.getAttribute("points") ?? "").trim().split(/\s+/).length);
      expect(n).toBe(w.s_mm.length);
      expect(w.s_mm.length).toBe(w.frame_hi - w.frame_lo + 1);
    }
    // The playhead is on the frame the viewer shows, across a spread of seeks.
    for (let j = 0; j < clip.frames.length; j += 17) {
      const at = await seek(page, clip.frames[j].t);
      expect(at.frame).toBe(clip.frames[j].f);
      await expect(page.locator("[data-playhead]")).toHaveAttribute("data-frame", String(at.frame));
    }
    await seek(page, clip.frames[0].t);
    const first = await page.locator("[data-playhead]").evaluate((el) => Number(el.getAttribute("x1")));
    await seek(page, clip.frames[clip.frames.length - 1].t);
    const last = await page.locator("[data-playhead]").evaluate((el) => Number(el.getAttribute("x1")));
    expect(last).toBeGreaterThan(first);
    // The hook player has a skeleton in every frame of his window: nothing painted from nothing.
    const hook = clip.windows![0];
    for (const frame of clip.frames.filter((f) => f.f >= hook.frame_lo && f.f <= hook.frame_hi)) {
      const entry = frame.p.find((e) => e[0] === hook.player);
      expect(entry?.[4], `frame ${frame.f}`).toBeTruthy();
    }
  }
});

test("a followed player who drops out of a whole-match clip leaves an empty panel, never the last body", async ({
  page,
}) => {
  test.skip(!EXPOSED, "window.__pose exists only in dev and test builds");
  const summary = await publishedSummary(page);
  await open(page);
  const lit = () =>
    page.evaluate(() => {
      const c = document.querySelector<HTMLCanvasElement>(".pose-follow canvas")!;
      const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i]) n++;
      return n;
    });
  for (const record of summary.clips.filter((c) => c.kind === "hook")) {
    const clip = (await (await page.request.get(`/data/${record.file}`)).json()) as PoseClip;
    // A player with a skeleton in one frame and no entry in the next: the clip lists only those with a pose.
    let k = -1;
    let gone = -1;
    for (let j = 0; j + 1 < clip.frames.length && k < 0; j++) {
      const next = new Set(clip.frames[j + 1].p.map((e) => e[0]));
      const e = clip.frames[j].p.find((x) => x[4] !== null && !next.has(x[0]));
      if (e) [k, gone] = [j, e[0]];
    }
    expect(k, `a player who drops out in ${record.file}`).toBeGreaterThanOrEqual(0);
    const other = clip.frames[k + 1].p.find((e) => e[0] !== gone && e[4] !== null)![0];
    await page.getByLabel("Clip", { exact: true }).selectOption(record.file);
    await page.waitForFunction((f) => window.__pose?.state === "idle" && window.__pose.frame === f, clip.frames[0].f);
    await seek(page, clip.frames[k].t);
    await page.getByLabel("Player", { exact: true }).selectOption(String(gone));
    await page.waitForFunction((i) => window.__pose?.player?.i === i, gone);
    expect((await pose(page)).player).toEqual({ i: gone, shows: "skeleton" });
    expect(await lit()).toBeGreaterThan(0);
    // The frame after: he is not listed, so the panel is empty and says so.
    await seek(page, clip.frames[k + 1].t);
    await page.waitForFunction((i) => window.__pose?.player?.shows === "absent" && window.__pose.player.i === i, gone);
    await expect(page.locator(".pose-follow")).toHaveAttribute("data-follow", "absent");
    await expect(page.locator(".pose-follow p")).toContainText("nothing is drawn");
    expect(await lit(), "the last body is still on the panel").toBe(0);
    // Another player, then the absent one again: never the other's body under his name.
    await page.getByLabel("Player", { exact: true }).selectOption(String(other));
    await page.waitForFunction((i) => window.__pose?.player?.i === i && window.__pose.player.shows === "skeleton", other);
    expect(await lit()).toBeGreaterThan(0);
    await page.getByLabel("Player", { exact: true }).selectOption(String(gone));
    await page.waitForFunction((i) => window.__pose?.player?.i === i && window.__pose.player.shows === "absent", gone);
    expect(await lit(), "another player's body under his name").toBe(0);
  }
});

// The three states the page has a branch for, each handed to it as a file (as /tracking/runs is).
for (const name of ["alive", "unreplicated", "dead"] as const) {
  test(`the ${name} branch shows its own state, with its figures from the file`, async ({ page }) => {
    const summary = fixture(name);
    const { errors, clips } = await openWith(page, summary);
    const status = page.locator("[data-section=status]");
    await expect(status).toHaveAttribute("data-status", summary.status);
    await expect(status).toHaveAttribute("data-dead-at", summary.dead_at ?? "");
    await expectFigures(page, summary, await clipOf(page));
    // The word that tells the states apart is in the text, and only the right one.
    const text = (await status.innerText()).trim();
    if (summary.status === "alive") expect(text).toMatch(/^Alive\./);
    if (summary.status === "unreplicated") expect(text).toMatch(/^Not replicated by coverage; not dead\./);
    if (summary.status === "dead") expect(text).toMatch(new RegExp(`^Dead at ${summary.dead_at}`));
    if (summary.status !== "alive") expect(text).not.toMatch(/^Alive/);
    if (summary.status !== "dead") expect(text).not.toMatch(/^Dead/);
    // Tables where the project lives or is unreplicated, none where it died; the viewer in all three.
    await expect(page.locator("[data-section=tables]")).toHaveCount(summary.tables === null ? 0 : 1);
    await expect(page.locator("[data-section=no-tables]")).toHaveCount(summary.tables === null ? 1 : 0);
    await expect(page.locator("figure.pose-viewer")).toBeVisible();
    await expect(page.locator("aside.pose-limits [data-limit]")).toHaveCount(3);
    // The clips of the file: a hook paints its window, a stretch has none to paint.
    for (const record of summary.clips) {
      await page.getByLabel("Clip", { exact: true }).selectOption(record.file);
      await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "true");
      await expect(page.locator("[data-section=clip] [data-clip-fig='selection.rule']")).toHaveText(
        record.selection.rule,
      );
      await expect(page.locator("[data-signal]")).toHaveCount(record.kind === "hook" ? 1 : 0);
      await expectFigures(page, summary, clips.get(record.file)!);
    }
    expect(await page.locator("main").innerHTML()).not.toMatch(FORBIDDEN);
    const prose = await proseOf(page);
    expect(prose.match(/\d+/g), "a figure typed into the prose").toBeNull();
    expect(errors).toEqual([]);
  });
}

// The publisher's own files for a project dead on 1925299 (M1, M2) or at the noise, and the one
// dead at M4: each says what killed it and shows no null where a number was never made.
for (const name of ["dead-m1", "dead-m2", "dead-noise", "dead"] as const) {
  test(`the ${name} file says what killed the project and shows no empty number`, async ({ page }) => {
    const summary = fixture(name);
    const { errors, clips } = await openWith(page, summary);
    const status = page.locator("[data-section=status]");
    await expect(status).toHaveAttribute("data-status", "dead");
    await expect(status).toHaveAttribute("data-dead-at", summary.dead_at!);
    await expect(status).toHaveText(
      summary.dead_at === "noise"
        ? /^Dead at the noise/
        : new RegExp(`^Dead at ${summary.dead_at}${summary.dead_at === "M1" ? "[.]" : ", by "}`),
    );
    // M2 and M4 name the sub-criterion (`dies_at`) that decided it, in the file's words and ours.
    if (summary.dead_at === "M2" || summary.dead_at === "M4") {
      const at = summary.dead_at === "M4" ? "verdict.confirmation.m4.dies_at" : "verdict.dies_at";
      const reason = resolve(summary, at) as string;
      expect(reason).toMatch(/^m2_/);
      await expect(status.locator(`[data-fig="${at}"]`)).toHaveText(reason);
      await expect(status).toContainText("propagated sd is larger");
    }
    await expectFigures(page, summary, await clipOf(page));
    await expect(page.locator("[data-section=no-tables]")).toHaveCount(1);
    const protocol = page.locator("[data-section=protocol]");
    await expect(protocol).not.toContainText("null");
    await expect(page.locator("main")).not.toContainText("null");
    if (summary.dead_at === "noise") await expect(protocol).toContainText("never frozen");
    else await expect(protocol.locator("[data-fig='protocol.width']")).toHaveText(String(summary.protocol.width));
    // The clips it names are stretches, drawn in the viewer without a window.
    const record = summary.clips[0];
    await page.getByLabel("Clip", { exact: true }).selectOption(record.file);
    await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "true");
    await expectFigures(page, summary, clips.get(record.file)!);
    await expect(page.locator("[data-signal]")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

for (const [width, shown] of WIDTHS.flatMap((w) => [w, w].map((x, k) => [x, k === 0 ? "sample" : "hook"] as const))) {
  test(`/tracking/pose at ${width} px with the ${shown} clip: no sideways scroll, no overlaps, text of 16 px or more`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await open(page);
    let clip = await clipOf(page);
    if (shown === "hook") {
      const record = (await publishedSummary(page)).clips[0];
      clip = (await (await page.request.get(`/data/${record.file}`)).json()) as PoseClip;
      await page.getByLabel("Clip", { exact: true }).selectOption(record.file);
      await expect(page.locator("[data-signal]")).toBeVisible();
    }
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
    console.log(`/tracking/pose at ${width} px: limits ${a.right <= b.left + 0.5 ? "beside" : "below"} the viewer`);
  });
}

test("the bytes /tracking/pose transfers, printed with no verdict, the clip apart", async ({ page }) => {
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
  console.log(`/tracking/pose: ${rest} bytes transferred without the clip (${script} of them scripts); the clip ${clip} bytes`);
  expect(clip).toBeGreaterThan(0);
});

test("the clip is fetched when asked for, not at load (task 158)", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r: Request) => asked.push(new URL(r.url()).pathname));
  await page.goto("/tracking/pose");
  await page.waitForLoadState("networkidle");
  const summary = (await (await page.request.get(SUMMARY)).json()) as PoseSummary;
  const button = page.getByRole("button", { name: /Load the clip/ });
  await expect(button).toBeVisible();
  // The button says what the clip weighs: pose.json's bytes, 1 decimal, SI.
  await expect(button).toContainText(`${(summary.phase406.bytes / 1e6).toFixed(1)} MB`);
  await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "false");
  expect(asked.filter((u) => u.startsWith("/data/pose/")), "no clip before the ask").toEqual([]);
  expect(asked).toContain(SUMMARY);

  await button.click();
  await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "true");
  expect(asked.filter((u) => u.startsWith("/data/pose/"))).toEqual([CLIP]);
  await expect(button).toHaveCount(0);
});

test("the home page links to /tracking/pose", async ({ page }) => {
  await page.goto("/");
  const link = page.getByRole("link", { name: "Body pose", exact: true });
  await expect(link).toHaveAttribute("href", "/tracking/pose");
  await link.click();
  await expect(page).toHaveURL(/\/tracking\/pose$/);
  await page.getByRole("button", { name: /Load the clip/ }).click();
  await expect(page.locator("main.pose")).toHaveAttribute("data-loaded", "true");
});
