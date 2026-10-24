// Every figure the text of lesson 7 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are pass.json and the ball and players of its example possession, at the decimals published.
import { shown } from "./expose";
import { chord, path, perSecond } from "./pass";
import type { PassExample, PassFile, PassMatch } from "./pass-data";

const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;
const sum = (m: readonly PassMatch[], f: (r: PassMatch) => number) => m.reduce((s, r) => s + f(r), 0);
const planar = (a: readonly number[], b: readonly number[]) => Math.hypot(b[0] - a[0], b[1] - a[1]);

// One pass of the example, from the published positions.
export function passFigures(ex: PassExample, fps: number) {
  const c = chord(ex.ball[0], ex.ball[ex.ball.length - 1]);
  const p = path(ex.ball);
  const n = ex.entry.frames;
  return {
    frames: n,
    seconds: shown(n / fps, 2),
    distance_m: shown(ex.entry.distance_m, 2),
    separation_m: shown(planar(ex.passer[0], ex.receiver[0]), 2),
    chord_m: shown(c, 2),
    path_m: shown(p, 2),
    path_pct: shown(100 * (p / c - 1), 1),
    chord_speed: shown(perSecond(c, n, fps), 2),
    distance_speed: shown(perSecond(ex.entry.distance_m, n, fps), 2),
    share_pct: shown((100 * c) / ex.entry.distance_m, 0),
    from_passer_m: shown(planar(ex.passer[0], ex.ball[0]), 2),
    to_receiver_m: shown(planar(ex.receiver[1], ex.ball[ex.ball.length - 1]), 2),
    receiver_moved_m: shown(planar(ex.receiver[0], ex.receiver[1]), 2),
    z_min: shown(Math.min(...ex.ball.map((b) => b[2])), 2),
  };
}

export function lessonPassFigures(file: PassFile, examples: readonly PassExample[]) {
  const passes = examples.map((ex) => passFigures(ex, file.fps));
  // The pass with the longest path for its chord: the bounce of the example.
  const bounce = passes.reduce((best, p, i) => (p.path_pct > passes[best].path_pct ? i : best), 0);
  const m = file.matches;
  const [chordLo, chordHi] = range(m.map((r) => r.chord_speed_median));
  const [p90Lo, p90Hi] = range(m.map((r) => r.chord_speed_p90));
  const [distLo, distHi] = range(m.map((r) => r.distance_speed_median));
  const [shareLo, shareHi] = range(m.map((r) => r.chord_over_distance));
  const [ratioLo, ratioHi] = range(m.map((r) => r.path_over_chord));
  const [nLo, nHi] = range(m.map((r) => r.n));
  return {
    passes,
    example_n: passes.length,
    bounce: bounce + 1,
    // Every match.
    matches: m.length,
    chord_lo: chordLo,
    chord_hi: chordHi,
    p90_lo: p90Lo,
    p90_hi: p90Hi,
    dist_lo: distLo,
    dist_hi: distHi,
    share_lo: shown(100 * shareLo, 0),
    share_hi: shown(100 * shareHi, 0),
    path_pct_lo: shown(100 * (ratioLo - 1), 2),
    path_pct_hi: shown(100 * (ratioHi - 1), 2),
    n_lo: nLo,
    n_hi: nHi,
    measured: sum(m, (r) => r.n),
    complete: sum(m, (r) => r.complete),
    not_forward: sum(m, (r) => r.complete - r.forward),
    no_ball: sum(m, (r) => r.forward - r.n),
    separation_n: sum(m, (r) => r.separation_n),
    separation_gap: Math.max(...m.map((r) => r.separation_gap_max)),
    speed_ratio_lo: shown(Math.min(...m.map((r) => r.distance_speed_median / r.chord_speed_median)), 1),
    speed_ratio_hi: shown(Math.max(...m.map((r) => r.distance_speed_median / r.chord_speed_median)), 1),
  };
}

export type PassLessonFigures = ReturnType<typeof lessonPassFigures>;
