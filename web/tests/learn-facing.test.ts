import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Compass } from "../components/learn/facing/Compass";
import { Lesson } from "../components/learn/facing/Lesson";
import { PerPlayer } from "../components/learn/facing/PerPlayer";
import { CANVAS, INK } from "../components/learn/gravity/Plot";
import { display } from "../lib/learn/display";
import { BACK_DEG, centralSpeed, circular, circularVariance, facingDeg, headingDeg, MIN_FRAMES, MIN_SPEED_M_S, relativeDeg, SIDE_DEG, summarise, wrap, type XY } from "../lib/learn/facing";
import { CLIPS, FACING, playerFrames, publishedFigure } from "../lib/learn/facing-data";
import { DEMO_DEG, facingFigures } from "../lib/learn/facing-figures";
import fence from "../lib/learn/fence.json";
import { SOURCES } from "../lib/learn/sources";
import type { PoseClip } from "../lib/pose/types";

// Lesson 11: the arithmetic in `facing.ts`, the frames it reads from the clips in
// `facing-data.ts`, and the text as the server renders it.
//
// Mutations checked by hand, each restored:
// - `facingDeg` taking the normal on the far side of the nose (the sign of `side` flipped):
//   "reads the facing of a rotated skeleton exactly" fails (half a turn off on every angle).
// - `playerFrames` with the heading from the frame itself to the frame after, not centred:
//   "a synthetic player on a bending path" fails (the forward difference lags the tangent).
// - `wrap` into [−180, 180): "brings an angle into the half turn either side of zero" fails at 180.
// - `circular` averaging the angles instead of their unit vectors: "averages angles on the circle" fails.
// - "a median of 23.038°" typed in the text: "has no digit typed in the prose" fails.

const DEG = 180 / Math.PI;
// A skeleton facing `deg`: the left shoulder a quarter turn to the left of the facing, the right
// opposite, the nose `ahead` units in front of their midpoint (behind when negative).
function skeleton(deg: number, ahead = 15, halfWidth = 20): { left: XY; right: XY; nose: XY } {
  const u: XY = [Math.cos(deg / DEG), Math.sin(deg / DEG)];
  const leftward: XY = [-u[1], u[0]];
  return {
    left: [halfWidth * leftward[0], halfWidth * leftward[1]],
    right: [-halfWidth * leftward[0], -halfWidth * leftward[1]],
    nose: [ahead * u[0], ahead * u[1]],
  };
}

describe("facing.ts", () => {
  it("reads the facing of a rotated skeleton exactly, whichever shoulder is called left", () => {
    for (const deg of [-170, -90, -45, 0, 30, 90, 135, 180]) {
      const { left, right, nose } = skeleton(deg);
      expect(facingDeg(left, right, nose)).toBeCloseTo(wrap(deg), 9);
      expect(facingDeg(right, left, nose)).toBeCloseTo(wrap(deg), 9);
      // The nose behind the shoulders: the chest faces the other way.
      const back = skeleton(deg, -15);
      expect(facingDeg(back.left, back.right, back.nose)).toBeCloseTo(wrap(deg + 180), 9);
    }
  });

  it("gives no facing when the nose lies on the shoulder line or the shoulders coincide", () => {
    expect(facingDeg([-20, 0], [20, 0], [5, 0])).toBeNaN();
    expect(facingDeg([3, 3], [3, 3], [0, 9])).toBeNaN();
  });

  it("brings an angle into the half turn either side of zero", () => {
    expect(wrap(190)).toBe(-170);
    expect(wrap(-190)).toBe(170);
    expect(wrap(180)).toBe(180);
    expect(wrap(-180)).toBe(180);
    expect(wrap(540)).toBe(180);
    expect(wrap(0)).toBe(0);
    expect(relativeDeg(-170, 170)).toBe(20);
  });

  it("takes the heading and the speed from the frames either side, exactly on a bending path", () => {
    // x = t, y = t² in metres: the tangent at t has slope 2t, and the central difference over
    // ±dt gives it exactly; a forward difference would give 2t + dt.
    const dt = 0.04;
    for (const t of [0.5, 1, 2]) {
      const before: XY = [t - dt, (t - dt) ** 2];
      const after: XY = [t + dt, (t + dt) ** 2];
      expect(headingDeg(before, after)).toBeCloseTo(Math.atan(2 * t) * DEG, 10);
      expect(centralSpeed(before, after, dt)).toBeCloseTo(Math.hypot(1, 2 * t), 10);
    }
  });

  it("averages angles on the circle, with the resultant length as their agreement", () => {
    expect(circular(DEMO_DEG).mean).toBeCloseTo(180, 10);
    expect(circular(DEMO_DEG).resultant).toBeCloseTo(Math.cos(10 / DEG), 12);
    expect(circular([10, 20]).mean).toBeCloseTo(15, 10);
    expect(circular([44]).resultant).toBeCloseTo(1, 12);
    expect(circular([0, 90, 180, -90]).resultant).toBeLessThan(1e-12);
    expect(circularVariance([-90, 0, 90])).toBeCloseTo(2 / 3, 12);
  });

  it("summarises frames: the median of the size, the shares past the two floors", () => {
    const frames = [10, -20, 50, -100, 170].map((relative, f) => ({ f, speed: 3, facing: relative, heading: 0, relative }));
    const s = summarise(frames);
    expect(s.frames).toBe(5);
    expect(s.median_abs).toBe(50);
    expect(s.off_pct).toBe(60);
    expect(s.back_pct).toBe(20);
    expect(s.circ_var).toBeCloseTo(circularVariance(frames.map((x) => x.relative)), 12);
    expect([SIDE_DEG, BACK_DEG, MIN_SPEED_M_S, MIN_FRAMES]).toEqual([45, 135, 2, 25]);
  });
});

// A clip with one player on x = 20k, y = 2k² cm (the tangent's slope at k is k/5), facing 30°
// in every frame, with no skeleton in frame 5 and the player missing from frame 9.
function syntheticClip(): PoseClip {
  const names = ["nose", "a", "b", "c", "d", "e", "lShoulder", "rShoulder"];
  const { left, right, nose } = skeleton(30);
  const joint = ([x, y]: XY) => [x, y, 150];
  const xyz = [joint(nose), [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], joint(left), joint(right)];
  const frames = Array.from({ length: 12 }, (_, k) => ({
    f: 100 + k,
    t: 40 * k,
    ball: [0, 0, 1],
    p: k === 9 ? [] : [[0, 20 * k, 2 * k * k, null, k === 5 ? null : [xyz, xyz.map(() => 80)]]],
  }));
  return { fps: 25, joints: names, players: [{ player_id: 1, team_id: 2, number: 3 }], windows: [{ player: 0 }], frames } as unknown as PoseClip;
}

describe("facing-data.ts", () => {
  it("a synthetic player on a bending path: centred headings, and the frames the rules leave out", () => {
    const frames = playerFrames(syntheticClip(), 0);
    // Frames 0 and 11 have no neighbour on one side; 5 has no skeleton; 8, 9 and 10 lose frame 9.
    expect(frames.map((x) => x.f - 100)).toEqual([1, 2, 3, 4, 6, 7]);
    for (const x of frames) {
      const k = x.f - 100;
      expect(x.facing).toBeCloseTo(30, 9);
      expect(x.heading).toBeCloseTo(Math.atan(k / 5) * DEG, 9);
      expect(x.relative).toBeCloseTo(wrap(30 - Math.atan(k / 5) * DEG), 9);
      expect(x.speed).toBeCloseTo(Math.hypot(40, 8 * k) / 100 / 0.08, 9);
    }
  });

  it("drops a frame below the floor of speed", () => {
    const clip = syntheticClip();
    // Frames 1 to 3 nearly held: 2 moves two centimetres by one over its two neighbours, under
    // the floor but not still; 1 and 3 keep a neighbour that moved.
    const slow: Record<number, [number, number]> = { 1: [40, 8], 2: [40, 8], 3: [42, 9] };
    for (const [k, [x, y]] of Object.entries(slow)) {
      clip.frames[Number(k)].p[0][1] = x;
      clip.frames[Number(k)].p[0][2] = y;
    }
    expect(Math.hypot(2, 1) / 100 / 0.08).toBeLessThan(MIN_SPEED_M_S);
    expect(playerFrames(clip, 0).map((x) => x.f - 100)).toEqual([1, 3, 4, 6, 7]);
  });

  it("reads both clips: the hook player and every row over the floor, each frame self-consistent", () => {
    expect(FACING.map((c) => c.match_id)).toEqual(Object.values(CLIPS).map((c) => c.match_id));
    for (const c of FACING) {
      expect(c.hook.frames.length).toBeGreaterThanOrEqual(MIN_FRAMES);
      expect(c.players.length).toBeGreaterThanOrEqual(10);
      expect(c.players.map((p) => p.index)).toEqual([...c.players.map((p) => p.index)].sort((a, b) => a - b));
      expect(c.players.some((p) => p.index === c.hook.index)).toBe(true);
      for (const p of c.players) expect(p.frames).toBeGreaterThanOrEqual(MIN_FRAMES);
      for (const x of c.hook.frames) {
        expect(x.speed).toBeGreaterThan(MIN_SPEED_M_S);
        expect(facingDeg(x.left, x.right, x.nose)).toBe(x.facing);
        expect(x.relative).toBe(relativeDeg(x.facing, x.heading));
        expect(x.relative).toBeGreaterThan(-180);
        expect(x.relative).toBeLessThanOrEqual(180);
      }
      const hookRow = c.players.find((p) => p.index === c.hook.index)!;
      expect(hookRow.frames).toBe(c.hook.frames.length);
      expect(hookRow.median_abs).toBe(summarise(c.hook.frames).median_abs);
    }
  });
});

// ---------------------------------------------------------------------------------------------
// The text.
// ---------------------------------------------------------------------------------------------
const SCRIPT = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "facing.py"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { script: SCRIPT }));
const FIGURES = facingFigures(FACING) as unknown as Record<string, unknown>;

const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (html: string, tags: string[]) =>
  tags.reduce((h, tag) => h.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), html);
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(
  drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]),
);
const at = (root: unknown, path: string) => path.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], root);

describe("the text of lesson 11", () => {
  it("prints every data-fig as its file or the lesson's arithmetic has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(100);
    const wrong = figs.filter(([name, shown]) => {
      // The figures' own readouts (`learn.compass.*`) live in their state; checked below.
      if (/^learn\.compass\./.test(name)) return false;
      const value = name.startsWith("learn.") ? at(FIGURES, name.slice(6)) : publishedFigure(name);
      return value === undefined || shown !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,20}\d+.{0,20}/g)).toBeNull();
  });

  it("has none of the fence's forbidden keys outside a quote or a citation, no held-out id, no vetted phrase", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
    for (const phrase of ["second difference", "straight line", "constant speed", "time to impact", "detected", "pressure", "defensive line", "width"]) {
      expect(outside).not.toContain(phrase);
    }
  });

  // That every source is cited by some lesson is checked across the series in learn-lesson.test.ts.
  it("cites only sources.ts", () => {
    const urls = Object.values(SOURCES).map((s) => s.url);
    const hrefs = [...HTML.matchAll(/<cite><a href="([^"]+)"/g)].map((m) => entities(m[1]));
    expect(hrefs.filter((h) => !urls.includes(h))).toEqual([]);
  });

  it("quotes every source it cites with a quote, word for word as sources.ts has it", () => {
    // Code in a quote renders as <code>, so the words are compared without their spacing.
    const squash = (s: string) => s.replace(/\s+/g, "");
    const quotes = [...HTML.matchAll(/<q>([\s\S]*?)<\/q>/g)].map((m) => squash(text(m[1])));
    for (const id of ["skillcorner-bodypose-joints", "skillcorner-bodypose-interpolated", "skillcorner-bodypose-separate", "scipy-circmean", "scipy-circvar"]) {
      expect(quotes).toContain(squash(SOURCES[id].quote!.replace(/`/g, "")));
    }
  });

  it("shows the script it was checked with", () => {
    expect(text(HTML)).toContain("def facing_deg(left: list[float], right: list[float], nose: list[float]) -> float | None:");
  });

  it("is between 1,300 and 2,300 words: its figures counted, its formulas, script and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 11: ${words} words`);
    expect(words).toBeGreaterThanOrEqual(1300);
    expect(words).toBeLessThanOrEqual(2300);
  });
});

// ---------------------------------------------------------------------------------------------
// The figures.
// ---------------------------------------------------------------------------------------------
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));
const F = facingFigures(FACING);
const ROWS = Object.fromEntries(FACING.map((c) => [String(c.match_id), F.players[c.match_id]]));
const HOOKS = Object.fromEntries(FACING.map((c) => [String(c.match_id), c.hook.index]));

describe("the figures of lesson 11", () => {
  const markups = [html(Compass, { clips: FACING }), html(PerPlayer, { rows: ROWS, hooks: HOOKS })];

  it("draw every stroke and fill at 3:1 or more on the canvas, in lesson 1's inks", () => {
    const colours = markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none");
    expect(new Set(colours)).toEqual(new Set(Object.values(INK)));
    expect([...new Set(colours)].filter((c) => contrast(c, CANVAS) < 3)).toEqual([]);
  });

  it("open on the first clip's first frame and first row, printing the lesson's figures", () => {
    const cell = (m: string, name: string) => m.match(new RegExp(`data-fig="${name.replace(/\./g, "\\.")}">([^<]*)<`))?.[1];
    const [A] = FACING;
    const hook = F.hook[A.match_id];
    expect(cell(markups[0], "learn.compass.frame_id")).toBe(String(hook.first_frame_id));
    expect(cell(markups[0], "learn.compass.facing")).toBe(String(hook.first_facing));
    expect(cell(markups[0], "learn.compass.relative")).toBe(String(hook.first_relative));
    expect(cell(markups[0], "learn.compass.circ_mean")).toBe(String(hook.circ_mean));
    expect(cell(markups[0], "learn.compass.resultant")).toBe(String(hook.resultant));
    const first = F.players[A.match_id][0];
    expect(cell(markups[1], `learn.players.${A.match_id}.0.median_abs`)).toBe(String(first.median_abs));
    // One table per clip, a row per qualifying player, and the hook player marked in the plot.
    for (const c of FACING) {
      expect((markups[1].match(new RegExp(`<table[^>]*data-match="${c.match_id}"[\\s\\S]*?</table>`)) ?? [""])[0].match(/<tr data-row=/g)?.length).toBe(c.players.length);
    }
    expect(markups[1]).toContain('data-hook=""');
  });
});
