// Every figure the text of lesson 9 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are dribble.json and the ball's heights of its example possession, at the decimals published.
import { median } from "./cadence";
import { intervals, lowest, lowPoints, rhythm } from "./dribble";
import type { DribbleFile, DribbleMatch, TouchExample } from "./dribble-data";
import { shown } from "./expose";

const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;
const sum = (m: readonly DribbleMatch[], f: (r: DribbleMatch) => number) => m.reduce((s, r) => s + f(r), 0);

// One dribble of the touch, from the published heights.
export function dribbleRow(ex: TouchExample, i: number) {
  const f = ex.dribbles[i];
  const low = lowest(ex.z, ex.first, f, ex.reach);
  if (!low) throw new Error(`dribble ${i}: the possession lacks the ball near frame ${f}`);
  return {
    n: i + 1,
    t_s: shown((f - ex.start) / ex.fps, 2),
    gap_frames: i === 0 ? 0 : f - ex.dribbles[i - 1],
    gap_s: i === 0 ? 0 : shown((f - ex.dribbles[i - 1]) / ex.fps, 2),
    offset: low.k,
    low_z: shown(low.z, 2),
    low_frame: f + low.k,
  };
}

export function touchFigures(ex: TouchExample) {
  const dribbles = ex.dribbles.map((_, i) => dribbleRow(ex, i));
  const gaps = intervals(ex.dribbles).map((g) => g / ex.fps);
  const shared = dribbles.findIndex((d, i) => i > 0 && d.low_frame === dribbles[i - 1].low_frame);
  if (shared < 1) throw new Error("the touch has no two dribbles on one low point");
  const last = ex.dribbles.length - 1;
  // The height from the first dribble to the last: the signal whose rhythm is read.
  const signal = ex.z.slice(ex.dribbles[0] - ex.first, ex.dribbles[last] - ex.first + 1);
  if (signal.some((h) => h === null)) throw new Error("the touch lacks the ball's height at a frame");
  const peak = rhythm(signal as number[]);
  if (!peak) throw new Error("the touch's height has no first peak");
  // The low points of the height over the dribbles' windows.
  const span = ex.z.slice(ex.dribbles[0] - ex.reach - ex.first, ex.dribbles[last] + ex.reach - ex.first + 1) as number[];
  const med = median(gaps);
  return {
    dribbles,
    ex_n: dribbles.length,
    ex_intervals: gaps.length,
    ex_seconds: shown((ex.end - ex.start) / ex.fps, 2),
    ex_median_s: shown(med, 2),
    ex_rate: shown(1 / med, 2),
    ex_low_points: lowPoints(span).length,
    ex_low_median: shown(median(dribbles.map((d) => d.low_z)), 2),
    ex_low_min: Math.min(...dribbles.map((d) => d.low_z)),
    ex_low_max: Math.max(...dribbles.map((d) => d.low_z)),
    ex_on_frame: dribbles.filter((d) => d.offset === 0).length,
    shared: shared + 1, // the second dribble of the pair, from one
    shared_first: shared,
    shared_gap_frames: dribbles[shared].gap_frames,
    shared_gap_s: dribbles[shared].gap_s,
    shared_z: dribbles[shared].low_z,
    ac_samples: signal.length,
    ac_first_negative: peak.firstNegative,
    ac_k: peak.k,
    ac_ratio: shown(peak.ratio, 3),
    ac_lag: shown(peak.lag, 2),
    ac_period_s: shown(peak.lag / ex.fps, 2),
    ac_rate: shown(ex.fps / peak.lag, 2),
  };
}

export function lessonDribbleFigures(file: DribbleFile, ex: TouchExample) {
  const m = file.matches;
  const [medLo, medHi] = range(m.map((r) => r.interval_median_s));
  const [p10Lo, p10Hi] = range(m.map((r) => r.interval_p10_s));
  const [p90Lo, p90Hi] = range(m.map((r) => r.interval_p90_s));
  const [t3Lo, t3Hi] = range(m.map((r) => r.touches_3));
  const [nLo, nHi] = range(m.map((r) => r.intervals));
  const [nearLo, nearHi] = range(m.map((r) => r.near_pct));
  const [edgeLo, edgeHi] = range(m.map((r) => r.edge_pct));
  const [lowLo, lowHi] = range(m.map((r) => r.low_z_median));
  const [sharedLo, sharedHi] = range(m.map((r) => r.shared_low));
  const sharedPct = m.map((r) => (100 * r.shared_low) / r.pairs);
  return {
    ...touchFigures(ex),
    matches: m.length,
    med_lo: medLo,
    med_hi: medHi,
    rate_lo: shown(1 / medHi, 2),
    rate_hi: shown(1 / medLo, 2),
    p10_lo: p10Lo,
    p10_hi: p10Hi,
    p90_lo: p90Lo,
    p90_hi: p90Hi,
    touches_lo: t3Lo,
    touches_hi: t3Hi,
    intervals_lo: nLo,
    intervals_hi: nHi,
    intervals: sum(m, (r) => r.intervals),
    dribbles_all: sum(m, (r) => r.dribbles),
    windows: sum(m, (r) => r.windows),
    no_window: sum(m, (r) => r.dribbles - r.windows),
    offset_zero: m.filter((r) => r.offset_median === 0 && r.offset_abs_median === 0).length,
    near_lo: nearLo,
    near_hi: nearHi,
    edge_lo: edgeLo,
    edge_hi: edgeHi,
    low_lo: lowLo,
    low_hi: lowHi,
    shared_lo: sharedLo,
    shared_hi: sharedHi,
    shared_pct_lo: shown(Math.min(...sharedPct), 1),
    shared_pct_hi: shown(Math.max(...sharedPct), 1),
    pairs: sum(m, (r) => r.pairs),
    shared_all: sum(m, (r) => r.shared_low),
  };
}

export type DribbleLessonFigures = ReturnType<typeof lessonDribbleFigures>;
