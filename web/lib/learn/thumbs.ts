// The drawing beside each lesson on /learn (task 182): a small picture of what the lesson works on,
// drawn at build time from the lesson's own data module, so no two are alike and none is typed.
// Each is a list of marks in a 160 by 100 box with no text; the index shows it beside the title and
// hides it from screen readers, since every fact it shows is the lesson's own and printed there.
import { HOOKS } from "./cadence-data";
import { fitLine, lineAt } from "./clock";
import { CLOCK_EXAMPLES } from "./clock-data";
import { HOME_STEMS, possession } from "./coordinates-data";
import { TOUCH } from "./dribble-data";
import { ENTRY, ENTRY_SAMPLES } from "./entry-data";
import { CLASSES, EXPECTED } from "./expected-data";
import { circular } from "./facing";
import { FACING } from "./facing-data";
import { fitQuadratic, type Quadratic } from "./gravity";
import { GRAVITY_HOOK } from "./gravity-data";
import { PASS_EXAMPLES } from "./pass-data";
import { expSurvival, quantile, survival } from "./possession";
import { durations, POSSESSION, spells } from "./possession-data";
import { REBOUND } from "./rebound-data";
import { differenceWeights, estimate } from "./speed";
import { SPEED_EXAMPLE } from "./speed-data";
import { basketballPrimitives, FIBA } from "../geometry/basketball";
import { footballPrimitives } from "../geometry/football";
import type { Primitive } from "../geometry/primitives";

export const THUMB = { w: 160, h: 100, pad: 8 } as const;

// ink: the lesson's data (cyan); alt: what it is set against (magenta); hi: a point or a line read
// off it (white); axis: a court, a pitch or a baseline (slate); band: a span (a cyan veil).
export type Tone = "ink" | "alt" | "hi" | "axis" | "band";
export type Pt = readonly [number, number];
export type Mark =
  | { kind: "stroke"; d: string; tone: Tone; dashed?: boolean }
  | { kind: "fill"; d: string; tone: Tone }
  | { kind: "rect"; x: number; y: number; w: number; h: number; tone: Tone }
  | { kind: "dots"; at: readonly Pt[]; r: number; tone: Tone };

const { w: W, h: H, pad: P } = THUMB;
const r1 = (v: number) => Math.round(v * 10) / 10;
const lin = (d0: number, d1: number, r0: number, r1v: number) => (v: number) =>
  d1 === d0 ? (r0 + r1v) / 2 : r0 + ((v - d0) / (d1 - d0)) * (r1v - r0);
const extent = (xs: readonly number[]): [number, number] => [Math.min(...xs), Math.max(...xs)];
const steps = (a: number, b: number, n: number) => Array.from({ length: n + 1 }, (_, i) => a + ((b - a) * i) / n);

// A polyline through the points; a null breaks it.
export function poly(points: readonly (Pt | null)[]): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${r1(p[0])} ${r1(p[1])}`;
    pen = true;
  }
  return d;
}

// A frame in metres with the same scale on both axes, the box's centre on the middle of the extent.
function metreFrame(xs: readonly number[], ys: readonly number[], margin: number) {
  const [x0, x1] = extent(xs);
  const [y0, y1] = extent(ys);
  const k = Math.min((W - 2 * P) / (x1 - x0 + 2 * margin), (H - 2 * P) / (y1 - y0 + 2 * margin));
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return { k, X: (v: number) => W / 2 + (v - cx) * k, Y: (v: number) => H / 2 + (v - cy) * k };
}

// A court's or a pitch's markings in a metre frame (y down, so an arc's angle grows clockwise).
function markings(prims: readonly Primitive[], f: { k: number; X: (v: number) => number; Y: (v: number) => number }): string {
  return prims
    .map((p) => {
      switch (p.kind) {
        case "line":
          return poly([
            [f.X(p.x1), f.Y(p.y1)],
            [f.X(p.x2), f.Y(p.y2)],
          ]);
        case "rect":
          return `${poly([
            [f.X(p.x), f.Y(p.y)],
            [f.X(p.x + p.w), f.Y(p.y)],
            [f.X(p.x + p.w), f.Y(p.y + p.h)],
            [f.X(p.x), f.Y(p.y + p.h)],
          ])}Z`;
        case "circle": {
          if (p.role === "spot") return "";
          const r = r1(p.r * f.k);
          return `M${r1(f.X(p.cx) - r)} ${r1(f.Y(p.cy))}a${r} ${r} 0 1 0 ${r1(2 * r)} 0a${r} ${r} 0 1 0 ${r1(-2 * r)} 0`;
        }
        case "arc": {
          const r = r1(p.r * f.k);
          const at = (a: number) => `${r1(f.X(p.cx + p.r * Math.cos(a)))} ${r1(f.Y(p.cy + p.r * Math.sin(a)))}`;
          return `M${at(p.start)}A${r} ${r} 0 ${p.end - p.start > Math.PI ? 1 : 0} 1 ${at(p.end)}`;
        }
      }
    })
    .join("");
}

// Lesson 1: the hook flight's samples, the parabola fitted to them, and the same start at standard
// gravity (the samples' own `z_real_m`, fitted the same way), as lesson 1's fit figure draws them.
function gravity(): Mark[] {
  const { t_s: t, z_data_m: z, z_real_m: zReal } = GRAVITY_HOOK;
  const [t0, t1] = extent(t);
  const ts = steps(t0, t1, 40);
  const at = (q: Quadratic, v: number) => q.c + q.b * v + q.a * v * v;
  const fit = fitQuadratic(t, z);
  const standard = fitQuadratic(t, zReal);
  const [z0, z1] = extent([...z, ...ts.map((v) => at(fit, v)), ...ts.map((v) => at(standard, v))]);
  const X = lin(t0, t1, P, W - P);
  const Y = lin(z0, z1, H - P, P);
  return [
    { kind: "stroke", d: poly(ts.map((v) => [X(v), Y(at(standard, v))])), tone: "alt", dashed: true },
    { kind: "stroke", d: poly(ts.map((v) => [X(v), Y(at(fit, v))])), tone: "ink" },
    { kind: "dots", at: t.map((v, i) => [r1(X(v)), r1(Y(z[i]))] as const), r: 1.8, tone: "hi" },
  ];
}

// Lesson 2: the example player's speed, the provider's field against a forward difference of the
// published positions, the noisiest of the lesson's three estimates.
function speed(): Mark[] {
  const { t_s: t, x, y, h, speed: provider } = SPEED_EXAMPLE;
  const noisy = estimate(x, y, differenceWeights("forward", h));
  const [, v1] = extent([...provider, ...noisy.filter((v): v is number => v !== null)]);
  const X = lin(t[0], t[t.length - 1], P, W - P);
  const Y = lin(0, v1, H - P, P);
  return [
    { kind: "stroke", d: poly([[P, H - P], [W - P, H - P]]), tone: "axis" },
    { kind: "stroke", d: poly(noisy.map((v, i) => (v === null ? null : [X(t[i]), Y(v)]))), tone: "alt" },
    { kind: "stroke", d: poly(provider.map((v, i) => [X(t[i]), Y(v)])), tone: "ink" },
  ];
}

// Lesson 3: the pitch and the court of the home's two possessions, in one frame of metres with the
// origin at the centre of both.
function coordinates(): Mark[] {
  const fb = possession(HOME_STEMS.football).surface;
  const bb = possession(HOME_STEMS.basketball).surface;
  const f = metreFrame([-fb.length_m / 2, fb.length_m / 2], [-fb.width_m / 2, fb.width_m / 2], 0);
  return [
    { kind: "stroke", d: markings(footballPrimitives(fb.length_m, fb.width_m), f), tone: "ink" },
    { kind: "stroke", d: markings(basketballPrimitives(bb.length_m, bb.width_m), f), tone: "alt" },
  ];
}

// Lesson 4: the example rebound's ten players where they stand, the way each is moving (half a
// second of their velocity), and the point the ball comes down, on the court's markings.
function rebound(): Mark[] {
  const ex = REBOUND.example;
  const court = possession(HOME_STEMS.basketball).surface;
  const f = metreFrame([ex.target[0], ...ex.players.map((p) => p.x)], [ex.target[1], ...ex.players.map((p) => p.y)], 1.2);
  const team = (name: string) => ex.players.filter((p) => p.team === name);
  const runs = ex.players.map((p) => poly([[f.X(p.x), f.Y(p.y)], [f.X(p.x + p.vx / 2), f.Y(p.y + p.vy / 2)]])).join("");
  const at = (ps: typeof ex.players) => ps.map((p) => [r1(f.X(p.x)), r1(f.Y(p.y))] as const);
  const [tx, ty] = [f.X(ex.target[0]), f.Y(ex.target[1])];
  return [
    { kind: "stroke", d: markings(basketballPrimitives(court.length_m, court.width_m), f), tone: "axis" },
    { kind: "stroke", d: runs, tone: "hi" },
    { kind: "dots", at: at(team("shooting")), r: 3, tone: "ink" },
    { kind: "dots", at: at(team("defending")), r: 3, tone: "alt" },
    { kind: "stroke", d: `M${r1(tx - 4)} ${r1(ty)}a4 4 0 1 0 8 0a4 4 0 1 0 -8 0`, tone: "hi" },
  ];
}

// Lesson 5: the first clip's hook window, the ankles' separation along the run and, around it, the
// spread its predicted errors give.
function cadence(): Mark[] {
  const { s_m: s, sigma_m: sigma } = HOOKS[0];
  const X = lin(0, s.length - 1, P, W - P);
  const [s0, s1] = extent([...s.map((v, i) => v - sigma[i]), ...s.map((v, i) => v + sigma[i])]);
  const Y = lin(s0, s1, H - P, P);
  const upper = s.map((v, i) => [X(i), Y(v + sigma[i])] as const);
  const lower = s.map((v, i) => [X(i), Y(v - sigma[i])] as const).reverse();
  return [
    { kind: "fill", d: `${poly([...upper, ...lower])}Z`, tone: "band" },
    { kind: "stroke", d: poly([[P, Y(0)], [W - P, Y(0)]]), tone: "axis" },
    { kind: "stroke", d: poly(s.map((v, i) => [X(i), Y(v)])), tone: "ink" },
  ];
}

// Lesson 6: the game clock against the video's time over an example possession (the one with a
// stretch the flag says is stopped, shaded), and the least-squares line through it.
function clock(): Mark[] {
  const ex = CLOCK_EXAMPLES.find((e) => e.stopped.length > 0) ?? CLOCK_EXAMPLES[0];
  const { t, clock: c } = ex;
  const fit = fitLine(t, c);
  const X = lin(t[0], t[t.length - 1], P, W - P);
  const Y = lin(...extent([...c, lineAt(fit, t[0]), lineAt(fit, t[t.length - 1])]), H - P, P);
  return [
    ...ex.stopped.map(([a, b]): Mark => ({ kind: "rect", x: r1(X(t[Math.round(a)])), y: P, w: r1(X(t[Math.round(b)]) - X(t[Math.round(a)])), h: H - 2 * P, tone: "band" })),
    { kind: "stroke", d: poly([[X(t[0]), Y(lineAt(fit, t[0]))], [X(t[t.length - 1]), Y(lineAt(fit, t[t.length - 1]))]]), tone: "alt", dashed: true },
    { kind: "stroke", d: poly(c.map((v, i) => [X(t[i]), Y(v)])), tone: "ink" },
  ];
}

// Lesson 7: the example's passes from above, the ball's path frame by frame and the chord from
// where it left to where it arrived, on the court's markings.
function pass(): Mark[] {
  const court = possession(HOME_STEMS.basketball).surface;
  const all = PASS_EXAMPLES.flatMap((p) => p.ball);
  const f = metreFrame(all.map((b) => b[0]), all.map((b) => b[1]), 1);
  return [
    { kind: "stroke", d: markings(basketballPrimitives(court.length_m, court.width_m), f), tone: "axis" },
    ...PASS_EXAMPLES.map((p): Mark => {
      const [a, b] = [p.ball[0], p.ball[p.ball.length - 1]];
      return { kind: "stroke", d: poly([[f.X(a[0]), f.Y(a[1])], [f.X(b[0]), f.Y(b[1])]]), tone: "hi", dashed: true };
    }),
    ...PASS_EXAMPLES.map((p): Mark => ({ kind: "stroke", d: poly(p.ball.map((b) => [f.X(b[0]), f.Y(b[1])])), tone: "ink" })),
    { kind: "dots", at: PASS_EXAMPLES.map((p) => [r1(f.X(p.ball[0][0])), r1(f.Y(p.ball[0][1]))] as const), r: 2.2, tone: "alt" },
  ];
}

// Lesson 8: the example shot from the side, its heights against the horizontal distance still to
// run to the rim's centre, and the rim at the file's height.
function entry(): Mark[] {
  const rim = ENTRY.example.rim_x;
  const d = ENTRY_SAMPLES.map((s) => Math.hypot(s.x - rim, s.y));
  const z = ENTRY_SAMPLES.map((s) => s.z);
  const [z0, z1] = extent([ENTRY.rim_height, ...z]);
  const k = Math.min((W - 2 * P) / (Math.max(...d) + 2 * FIBA.hoopRadius), (H - 2 * P) / (z1 - z0));
  const X = (v: number) => W - P - FIBA.hoopRadius * k - v * k;
  const Y = (v: number) => H - P - (v - z0) * k;
  return [
    { kind: "stroke", d: poly([[X(FIBA.hoopRadius), Y(ENTRY.rim_height)], [X(-FIBA.hoopRadius), Y(ENTRY.rim_height)]]), tone: "alt" },
    { kind: "dots", at: d.map((v, i) => [r1(X(v)), r1(Y(z[i]))] as const), r: 1.8, tone: "ink" },
  ];
}

// Lesson 9: the example touch's ball height frame by frame, each dribble the file finds a tick
// under it.
function dribble(): Mark[] {
  const { z, first, dribbles } = TOUCH;
  const X = lin(first, first + z.length - 1, P, W - P);
  const Y = lin(0, Math.max(...z.filter((v): v is number => v !== null)), H - P - 6, P);
  return [
    { kind: "stroke", d: poly([[P, Y(0)], [W - P, Y(0)]]), tone: "axis" },
    { kind: "stroke", d: dribbles.map((f) => poly([[X(f), H - P - 4], [X(f), H - P + 2]])).join(""), tone: "alt" },
    { kind: "stroke", d: poly(z.map((v, i) => (v === null ? null : [X(first + i), Y(v)]))), tone: "ink" },
  ];
}

// Lesson 10: basketball possessions as a survival curve, the share still going at each time, set
// against the exponential with the same median, out to twice the 90th percentile.
function possessionCurve(): Mark[] {
  const d = durations(spells(POSSESSION.basketball.timeline));
  const median = quantile(d, 0.5);
  const tMax = 2 * quantile(d, 0.9);
  const ts = steps(0, tMax, 80);
  const X = lin(0, tMax, P, W - P);
  const Y = lin(0, 1, H - P, P);
  return [
    { kind: "stroke", d: poly([[P, P], [P, H - P], [W - P, H - P]]), tone: "axis" },
    { kind: "stroke", d: poly(ts.map((t) => [X(t), Y(expSurvival(median, t))])), tone: "alt", dashed: true },
    { kind: "stroke", d: poly(ts.map((t) => [X(t), Y(survival(d, t))])), tone: "ink" },
  ];
}

// Lesson 11: the first clip's hook player as a rose of the relative angle, one wedge per thirty
// degrees, straight ahead at the top, and the mean resultant vector, as the lesson's compass draws it.
function facing(): Mark[] {
  const BIN = 30;
  const bins = 360 / BIN;
  const R = H / 2 - P;
  const [cx, cy] = [W / 2, H / 2];
  const at = (deg: number, r: number): Pt => [cx + r * Math.cos((deg * Math.PI) / 180), cy - r * Math.sin((deg * Math.PI) / 180)];
  const { frames } = FACING[0].hook;
  const counts = Array.from({ length: bins }, () => 0);
  for (const x of frames) counts[(((Math.floor((x.relative + BIN / 2) / BIN) % bins) + bins) % bins)]++;
  const top = Math.max(...counts);
  const wedges = counts
    .map((n, i) => {
      if (n === 0) return "";
      const r = (R * n) / top;
      const [a, b] = [90 + i * BIN - BIN / 2 + 2, 90 + i * BIN + BIN / 2 - 2].map((deg) => at(deg, r));
      return `M${cx} ${cy}L${r1(a[0])} ${r1(a[1])}A${r1(r)} ${r1(r)} 0 0 0 ${r1(b[0])} ${r1(b[1])}Z`;
    })
    .join("");
  const { mean, resultant } = circular(frames.map((x) => x.relative));
  return [
    { kind: "stroke", d: `M${cx - R} ${cy}a${R} ${R} 0 1 0 ${2 * R} 0a${R} ${R} 0 1 0 ${-2 * R} 0${poly([[cx, cy - R], [cx, cy + R]])}${poly([[cx - R, cy], [cx + R, cy]])}`, tone: "axis" },
    { kind: "fill", d: wedges, tone: "ink" },
    { kind: "stroke", d: poly([[cx, cy], at(90 + mean, R * resultant)]), tone: "hi" },
  ];
}

// Lesson 12: the first season's points per shot by zone class, each bar as wide as the class's
// share of the attempts, and the mean weighted by them across the box.
function expectedPoints(): Mark[] {
  const s = EXPECTED.seasons[0];
  const total = CLASSES.reduce((sum, c) => sum + s.league[c].n, 0);
  const Y = lin(0, Math.max(...CLASSES.map((c) => s.pps[c])), H - P, P);
  const tones: Record<(typeof CLASSES)[number], Tone> = { rim: "ink", mid: "axis", three: "alt" };
  let x = P;
  const bars = CLASSES.map((c): Mark => {
    const w = ((W - 2 * P) * s.league[c].n) / total;
    const bar: Mark = { kind: "rect", x: r1(x), y: r1(Y(s.pps[c])), w: r1(w - 2), h: r1(H - P - Y(s.pps[c])), tone: tones[c] };
    x += w;
    return bar;
  });
  return [...bars, { kind: "stroke", d: poly([[P, Y(s.mean)], [W - P, Y(s.mean)]]), tone: "hi", dashed: true }];
}

const DRAW: Record<string, () => Mark[]> = {
  gravity,
  speed,
  coordinates,
  rebound,
  cadence,
  clock,
  pass,
  entry,
  dribble,
  possession: possessionCurve,
  facing,
  "expected-points": expectedPoints,
};

// The marks of a lesson's drawing, or null for a lesson that has none yet.
export function thumbOf(slug: string): Mark[] | null {
  return DRAW[slug]?.() ?? null;
}
