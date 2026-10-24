import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClockFigure, readClock, START_MS } from "../components/learn/coordinates/ClockFigure";
import { FrameFigure, readAt, stepOf } from "../components/learn/coordinates/FrameFigure";
import { Lesson } from "../components/learn/coordinates/Lesson";
import { CANVAS } from "../components/learn/gravity/Plot";
import {
  affine,
  alphaAt,
  cornerTurn,
  det,
  FOOT_M,
  HALF_TURN,
  lerp,
  MIRROR_X,
  onCornerSurface,
  type Point,
  scaled,
  sharedClock,
  toCommon,
} from "../lib/learn/coordinates";
import {
  CLOCK_WINDOW_MS,
  clockTrack,
  coordinatesFigures,
  frameView,
  HOME_STEMS,
  MATCHES,
  PUBLISHED,
  publishedFigure,
  stemOf,
} from "../lib/learn/coordinates-data";
import fence from "../lib/learn/fence.json";
import { SOURCES } from "../lib/learn/sources";
import { ReplayEngine } from "../lib/replay/engine";

// Lesson 3: its arithmetic on synthetic points, its slice of the published files against those
// files read again from disk, and its text as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `lerp` as `a + b * alpha` (weights that do not add up to one): "commutes with an affine map"
//   fails on the shifted map.
// - `HALF_TURN` as the mirror [[-1, 0], [0, 1]]: "half a turn has determinant one" fails.
// - `lcm` as `a * b`: "two clocks share an instant every 200 ms" fails.
// - `alphaAt` as `(tb - t) / (tb - ta)`: "reads the replay's engine between samples" fails.
// - `stepOf` with `fy = 1` for every step: "turns both coordinates" fails.
// - A number typed into the prose of Lesson.tsx: "has no digit" fails.

const read = (...p: string[]) => JSON.parse(readFileSync(join(process.cwd(), ...p), "utf-8"));
const INDEX = read("public", "data", "index.json") as { possessions: { possession_id: string; match_id: string; file: string }[] };
const STATS = read("public", "data", "stats.json") as { tables: { table: string; sport: string; match_id: string; rows: number }[] };
const QUALITY = read("public", "data", "quality.json") as { checks: { clock: { match_id: string; metric: string; value: number; n: number }[] } };
const heldOut = (id: string) => fence.held_out.includes(id.replace(/^[a-z]+:/, ""));
const close = (a: Point, b: Point) => expect(Math.hypot(a[0] - b[0], a[1] - b[1])).toBeLessThan(1e-9);

// A seeded generator, so a failing case is the same case next time.
function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32) * 2 - 1;
}

describe("the arithmetic", () => {
  it("converts feet to metres by the exact factor and turns by the sign", () => {
    expect(toCommon([10, -5], FOOT_M, 1)).toEqual([3.048, -1.524]);
    close(toCommon([10, -5], FOOT_M, -1), [-3.048, 1.524]);
    expect(toCommon([7, 2], 1, 1)).toEqual([7, 2]);
  });

  it("half a turn has determinant one and the mirror minus one", () => {
    expect(det(HALF_TURN)).toBe(1);
    expect(det(MIRROR_X)).toBe(-1);
    expect(det(scaled(FOOT_M))).toBeCloseTo(FOOT_M ** 2, 12);
  });

  it("linear interpolation commutes with an affine map, shift included, and a sum of weights other than one does not", () => {
    const r = rng(3);
    const maps = [affine(scaled(-FOOT_M)), affine(scaled(1, MIRROR_X), [52.5, 34]), affine([[0.3, -1.2], [2, 0.7]], [-4, 9])];
    for (let n = 0; n < 200; n++) {
      const a: Point = [50 * r(), 30 * r()];
      const b: Point = [50 * r(), 30 * r()];
      const alpha = (r() + 1) / 2;
      for (const map of maps) close(map(lerp(a, b, alpha)), lerp(map(a), map(b), alpha));
    }
    // Weights of 0.6 and 0.6: the shift is counted twice, so the two orders part.
    const shifted = affine(scaled(1), [10, 0]);
    const both = (p: Point, q: Point): Point => [0.6 * p[0] + 0.6 * q[0], 0.6 * p[1] + 0.6 * q[1]];
    expect(shifted(both([1, 1], [2, 2]))[0]).not.toBeCloseTo(both(shifted([1, 1]), shifted([2, 2]))[0], 6);
  });

  it("two clocks of 25 and 10 Hz share an instant every 200 ms", () => {
    expect(sharedClock(25, 10)).toEqual({ stepA: 40, stepB: 100, shared: 200, everyA: 5, everyB: 2, missingOnA: 4, missingOnB: 1 });
    expect(sharedClock(25, 25).shared).toBe(40);
    expect(alphaAt(40, 80, 60)).toBe(0.5);
    expect(alphaAt(40, 40, 40)).toBe(0);
  });

  it("from a corner origin, negating leaves the surface and the turn about the centre does not", () => {
    const L = 105;
    const W = 68;
    const r = rng(7);
    for (let n = 0; n < 100; n++) {
      const p: Point = [(L / 2) * r(), (W / 2) * r()];
      const c = cornerTurn(p, L, W);
      close(c.turned, c.centred);
      expect(onCornerSurface(c.turned, L, W)).toBe(true);
      if (Math.abs(p[0]) < L / 2 && Math.abs(p[1]) < W / 2) expect(onCornerSurface(c.negated, L, W)).toBe(false);
    }
  });
});

describe("the published slice", () => {
  it("reads every published possession but those of a held-out match", () => {
    const allowed = INDEX.possessions.filter((p) => !heldOut(p.match_id)).map((p) => stemOf(p.file));
    expect(Object.keys(PUBLISHED).sort()).toEqual(allowed.sort());
    expect(Object.values(PUBLISHED).filter((p) => heldOut(p.match.match_id))).toEqual([]);
    expect(HOME_STEMS).toEqual({
      basketball: "bb_possessions_possession-114086-1-36",
      football: "fb_possession_1874553_1",
    });
  });

  it("has one row per match of stats.json's frames, held-out football left out, as the files have them", () => {
    const frames = STATS.tables.filter((r) => r.table === "frames");
    expect(MATCHES.map((m) => m.match_id).sort()).toEqual(frames.filter((r) => !heldOut(r.match_id)).map((r) => r.match_id).sort());
    expect(MATCHES.filter((m) => m.sport === "basketball")).toHaveLength(10);
    expect(MATCHES.filter((m) => m.sport === "football")).toHaveLength(10);
    for (const m of MATCHES) {
      const clock = QUALITY.checks.clock.find((c) => c.match_id === m.match_id && c.metric === "clock_step_exact_pct")!;
      expect([m.rows, m.steps, m.exact_pct]).toEqual([frames.find((r) => r.match_id === m.match_id)!.rows, clock.n, clock.value]);
      expect(m.minutes).toBeCloseTo(clock.n / (m.sport === "basketball" ? 25 : 10) / 60, 1);
    }
  });

  // DuckDB 1.5.5 over SkillCorner's raw 114086_tracking_data.jsonl.gz at wallClock 1199000 (the
  // second result of coordinates.sql), feet at two decimals: an artefact independent of the build.
  const RAW_FT: Record<string, Point> = {
    "bb:32336": [-35.99, -21.9],
    "bb:34992": [-28.66, 18.15],
    "bb:35096": [-25.43, 2.36],
    "bb:59135": [-33.35, 9.06],
    "bb:59137": [-27.5, -11.32],
    "bb:59139": [-36.65, -10.3],
    "bb:59153": [-22.57, -17.49],
    "bb:59155": [-27.02, 21.94],
    "bb:59156": [-35.4, 7.77],
    "bb:59295": [-12.74, 3.15],
    "bb:ball": [-29.25, 23.52],
  };

  it("divides the published metres back to the provider's feet within the bound the page prints", () => {
    const view = frameView(HOME_STEMS.basketball);
    const p = PUBLISHED[view.stem];
    const ids = new Map(p.entities.map((e) => [e.i, e.entity_id]));
    const { feet_bound } = coordinatesFigures();
    expect(view.entities).toHaveLength(Object.keys(RAW_FT).length);
    for (const e of view.entities) {
      const raw = RAW_FT[ids.get(e.i)!];
      const [x, y] = readAt(view, "delivered", e.x, e.y);
      expect(Math.abs(x - raw[0])).toBeLessThanOrEqual(feet_bound + 0.005 + 1e-9);
      expect(Math.abs(y - raw[1])).toBeLessThanOrEqual(feet_bound + 0.005 + 1e-9);
    }
  });

  it("gives the clock figure the ball in every frame of the window", () => {
    for (const stem of Object.values(HOME_STEMS)) {
      const track = clockTrack(stem);
      expect(track.frames).toHaveLength(CLOCK_WINDOW_MS / (1000 / track.rate) + 1);
      expect(track.frames.every((f) => f.o.length === 1 && f.o[0][0] === track.ball)).toBe(true);
    }
  });

  it("computes the figures the text quotes", () => {
    const F = coordinatesFigures();
    expect([F.frame_bb, F.frame_fb, F.max_rows_s_bb, F.max_rows_s_fb]).toEqual([29975, 29, 275, 230]);
    expect([F.team_period_ratio_bb, F.team_period_ratio_fb]).toEqual([2, 2]);
    expect(F.signs_plus + F.signs_minus).toBe(Object.keys(PUBLISHED).length);
    expect(F.surfaces_bb).toEqual([[28, 15]]);
    expect(F.corner.turned).toEqual([60.6, 29.09]);
  });
});

describe("the figures' readings", () => {
  const bb = frameView(HOME_STEMS.basketball);

  it("turns both coordinates, mirrors only x, and reads feet only as delivered", () => {
    const p = bb.entities[0];
    expect(readAt(bb, "metres", p.x, p.y)).toEqual([p.x, p.y]);
    expect(readAt(bb, "turn-own", p.x, p.y)).toEqual([bb.sign * p.x, bb.sign * p.y]);
    expect(readAt(bb, "turn-other", p.x, p.y)).toEqual([-bb.sign * p.x, -bb.sign * p.y]);
    expect(readAt(bb, "mirror-other", p.x, p.y)).toEqual([-bb.sign * p.x, p.y]);
    expect(readAt(bb, "delivered", p.x, p.y)[0]).toBeCloseTo(p.x / FOOT_M, 2);
    expect(stepOf(bb, "turn-other").attack).toBe(-1);
    expect(stepOf(bb, "turn-own").attack).toBe(1);
  });

  it("reads the replay's engine between samples, with the weights the formula gives", () => {
    for (const stem of Object.values(HOME_STEMS)) {
      const track = clockTrack(stem);
      const engine = new ReplayEngine(track);
      const step = 1000 / track.rate;
      for (const t of [0, START_MS, 333, 999, 1000]) {
        const r = readClock(track, engine, t);
        const k = Math.min(Math.floor(t / step), track.frames.length - 1);
        expect(r.ta).toBe(k * step);
        const xa = track.frames[k].o[0][1];
        const xb = track.frames[Math.min(k + 1, track.frames.length - 1)].o[0][1];
        const alpha = r.tb === r.ta ? 0 : (t - r.ta) / (r.tb - r.ta);
        expect(r.alpha).toBe(Number(alpha.toFixed(2)));
        expect(Math.abs(r.x - (xa + (xb - xa) * alpha))).toBeLessThanOrEqual(0.005 + 1e-9);
      }
    }
  });
});

// The page as the server renders it.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "coordinates.sql"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: SQL }));
const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&").replace(/&nbsp;| /g, " ");
const drop = (html: string, tags: string[]) =>
  tags.reduce((h, tag) => h.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), html);
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
// A figure as printed: thousands separators and a leading plus out, a minus sign as a hyphen.
export const normalise = (s: string) => s.replace(/,/g, "").replace(/−/g, "-").replace(/^\+/, "");
const PROSE = text(drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]));

describe("the text of lesson 3", () => {
  it("prints every data-fig as its file or its computation has it", () => {
    // The figures open on the court as delivered and on the clock's first instant.
    const bbView = frameView(HOME_STEMS.basketball);
    const player = bbView.entities.find((e) => e.i === bbView.highlight)!;
    const ball = bbView.entities.find((e) => e.role === "ball")!;
    const tracks = Object.values(HOME_STEMS).map((s) => clockTrack(s));
    const initial: Record<string, unknown> = {
      ...coordinatesFigures(),
      frame: { k: 1, player: readAt(bbView, "delivered", player.x, player.y), ball: readAt(bbView, "delivered", ball.x, ball.y) },
      clock: { t: START_MS, ...Object.fromEntries(tracks.map((t) => [t.sport, readClock(t, new ReplayEngine(t), START_MS)])) },
    };
    const dig = (o: unknown, path: string) => path.split(".").reduce<unknown>((at, k) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[k] : undefined), o);
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], normalise(entities(m[2]))] as const);
    expect(figs.length).toBeGreaterThan(90);
    const wrong = figs.filter(([name, shown]) => {
      const value = name.startsWith("learn.") ? dig(initial, name.slice(6)) : publishedFigure(name);
      return value === undefined || String(value) !== shown;
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit once figures, formulas, citations, quotes, code and tables are out", () => {
    expect(PROSE.match(/.{0,30}\d.{0,30}/g) ?? []).toEqual([]);
    const words = PROSE.split(/\s+/).filter((w) => /[A-Za-z]/.test(w)).length;
    console.log(`lesson 3: ${words} words of prose`);
    expect(words).toBeGreaterThanOrEqual(1500);
    expect(words).toBeLessThanOrEqual(2300);
  });

  it("holds none of the fence's forbidden keys outside a quote or a citation, and no held-out id", () => {
    const outside = text(drop(HTML, ["q", "cite"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
    for (const word of ["straight line", "second difference", "pressure", "defensive line", "width of the block"]) expect(outside).not.toContain(word);
  });

  // That every source is cited by some lesson is checked across the series in learn-lesson.test.ts.
  it("cites only sources.ts", () => {
    const urls = Object.values(SOURCES).map((s) => s.url);
    const hrefs = [...HTML.matchAll(/<cite><a href="([^"]+)"/g)].map((m) => entities(m[1]));
    expect(hrefs.filter((h) => !urls.includes(h))).toEqual([]);
  });

  it("draws every stroke and fill on the canvas at 3:1 or more", () => {
    const luminance = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => {
        const c = parseInt(hex.slice(i, i + 2), 16) / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const contrast = (a: string, b: string) => {
      const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    const views = Object.values(HOME_STEMS).map((s) => frameView(s));
    const markups = [
      renderToStaticMarkup(createElement(FrameFigure, { views, feetBound: 0.016 })),
      renderToStaticMarkup(createElement(ClockFigure, { tracks: Object.values(HOME_STEMS).map((s) => clockTrack(s)), shared: 200, windowMs: CLOCK_WINDOW_MS })),
    ];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(3);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
