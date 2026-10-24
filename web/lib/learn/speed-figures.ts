// Every figure the text of lesson 2 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are the example (the published possession at 1 cm and the provider's speed from speed.json),
// the rows of speed.json, and a synthetic parabola.
import { shown } from "./expose";
import { differenceWeights, estimate, gapTo, type Kind, parabolaPath, roundingBound, smoothed } from "./speed";
import type { SpeedExample, SpeedFile } from "./speed-data";

// The synthetic: a body speeding up at a constant 3 m/s², a brisk change of pace for a player
// (an illustration, not a measurement), sampled at the file's rate for one second.
const ACCEL = 3;
export const K_MAX = 15;
export const EXAMPLE_WINDOWS = Array.from({ length: (K_MAX + 1) / 2 }, (_, i) => 2 * i + 1);

export const exampleGap = (ex: SpeedExample, kind: Kind, k: number) =>
  gapTo(ex.speed, estimate(ex.x, ex.y, smoothed(differenceWeights(kind, ex.h), k)));

// The window of k central differences whose median gap is smallest; the first on a tie.
export const bestWindow = (rows: readonly { k: number; median: number }[]) =>
  rows.reduce((best, r) => (r.median < best.median ? r : best));

const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;

export function speedFigures(ex: SpeedExample, file: SpeedFile) {
  const h = ex.h;
  const central = exampleGap(ex, "central", 1);
  const forward = exampleGap(ex, "forward", 1);
  const backward = exampleGap(ex, "backward", 1);
  const shaw = exampleGap(ex, "backward", file.shaw_window);
  const byK = EXAMPLE_WINDOWS.map((k) => ({ k, median: exampleGap(ex, "central", k).median }));
  const exBest = bestWindow(byK);
  const peak = Math.max(...ex.speed);

  // The synthetic parabola: its speed at frame i is ACCEL · i · h exactly.
  const frames = 1 + Math.round(1 / h);
  const path = parabolaPath(ACCEL, h, frames);
  const flat = path.map(() => 0);
  const truth = path.map((_, i) => ACCEL * i * h);
  const synthGap = (kind: Kind) => gapTo(truth, estimate(path, flat, differenceWeights(kind, h))).max;

  const m = file.matches;
  const [rLo, rHi] = range(m.map((r) => r.r));
  const [gapLo, gapHi] = range(m.map((r) => r.median_gap));
  const [p99Lo, p99Hi] = range(m.map((r) => r.p99_gap));
  const [oneSidedLo, oneSidedHi] = range(m.flatMap((r) => [r.median_gap_forward, r.median_gap_backward]));
  const [ratioLo, ratioHi] = range(m.flatMap((r) => [r.median_gap_forward / r.median_gap, r.median_gap_backward / r.median_gap]));
  const best = m.map((r) => bestWindow(file.windows.map((k) => ({ k, median: r.by_window[String(k)] }))));
  const bestK = best[0].k;
  const [bestLo, bestHi] = range(best.map((b) => b.median));
  const [shawLo, shawHi] = range(m.map((r) => r.median_gap_shaw));
  const over = m.filter((r) => r.over_max > 0);

  const centralW = differenceWeights("central", h);
  const forwardW = differenceWeights("forward", h);

  return {
    frames: ex.speed.length,
    duration_s: shown(ex.t_s[ex.t_s.length - 1], 2),
    peak: shown(peak, 2),
    peak_frames_in: ex.speed.indexOf(peak),
    step_ms: shown(1000 * h, 0),
    half_step_ms: shown(500 * h, 0),
    resolution_cm: shown(100 * ex.resolution, 0),
    synth_accel: ACCEL,
    synth_forward_gap: shown(synthGap("forward"), 3),
    synth_central_gap: shown(synthGap("central"), 3),
    bound_forward: shown(roundingBound(forwardW, ex.resolution), 3),
    bound_central: shown(roundingBound(centralW, ex.resolution), 3),
    bound_central_speed: shown(Math.SQRT2 * roundingBound(centralW, ex.resolution), 3),
    ex_central_median: shown(central.median, 4),
    ex_central_max: shown(central.max, 3),
    ex_central_frames: central.frames,
    ex_forward_median: shown(forward.median, 4),
    ex_backward_median: shown(backward.median, 4),
    ex_best_k: exBest.k,
    ex_best_median: shown(exBest.median, 4),
    ex_k_max: K_MAX,
    ex_k_max_median: shown(byK[byK.length - 1].median, 4),
    ex_shaw_median: shown(shaw.median, 4),
    matches: m.length,
    r_lo: rLo,
    r_hi: rHi,
    gap_lo: gapLo,
    gap_hi: gapHi,
    p99_lo: p99Lo,
    p99_hi: p99Hi,
    one_sided_lo: oneSidedLo,
    one_sided_hi: oneSidedHi,
    one_sided_ratio_lo: shown(ratioLo, 1),
    one_sided_ratio_hi: shown(ratioHi, 1),
    best_k: bestK,
    best_k_matches: best.filter((b) => b.k === bestK).length,
    best_lo: bestLo,
    best_hi: bestHi,
    shaw_lo: shawLo,
    shaw_hi: shawHi,
    over_matches: over.length,
    over_rows: over.reduce((s, r) => s + r.over_max, 0),
    all_rows: m.reduce((s, r) => s + r.rows, 0),
  };
}

export type SpeedFigures = ReturnType<typeof speedFigures>;
