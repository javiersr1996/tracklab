// Every figure the text of lesson 5 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are the two hook windows and the fast-band rows of `pose.json` (`cadence-data.ts`); the
// constants are the pipeline's (`gait.py`: BAND_Z, DRAWS, SEED) or this lesson's (the scales).
import { shown } from "./expose";
import { autocorrelation, BAND_Z, cadenceHz, firstPeak, linearSd, mean, median, monteCarlo, sd } from "./cadence";
import type { HookWindow, PlayerRow } from "./cadence-data";

export const DRAWS = 200; // gait.py's DRAWS
export const SEED = 59; // gait.py's SEED, here the seed of one mulberry32 stream
export const SCALE_LOW = 0.25;
export const SCALE_HIGH = 2;

// What one window says, and what its predicted error does to it.
export function windowFigures(h: HookWindow) {
  const n = h.s_m.length;
  const peak = firstPeak(autocorrelation(h.s_m));
  if (!peak?.resolved) throw new Error(`${h.file}: the hook window has no resolved peak`);
  const lag = peak.k + peak.shift;
  const draws = monteCarlo(h.s_m, h.sigma_m, h.fps, DRAWS, SEED).filter(Number.isFinite);
  const linear = linearSd(h.s_m, h.sigma_m, h.fps);
  const at = (scale: number) => {
    const d = monteCarlo(h.s_m, h.sigma_m, h.fps, DRAWS, SEED, scale);
    const ok = d.filter(Number.isFinite);
    return { ratio: sd(ok) / (scale * linear), unresolved: d.length - ok.length };
  };
  const low = at(SCALE_LOW);
  const high = at(SCALE_HIGH);
  const repro = monteCarlo(h.joints_s_m, h.sigma_m, h.fps, DRAWS, SEED).filter(Number.isFinite);
  return {
    samples: n,
    seconds: n / h.fps,
    first_negative: peak.firstNegative,
    peak_k: peak.k,
    peak_ratio: shown(peak.ratio, 3),
    peak_band: shown(peak.band, 3),
    peak_shift: shown(peak.shift, 3),
    peak_lag: shown(lag, 3),
    stride_s: shown(lag / h.fps, 3),
    cadence: shown(cadenceHz(h.s_m, h.fps), 4),
    cadence_k: shown((2 * h.fps) / peak.k, 3),
    cadence_k_next: shown((2 * h.fps) / (peak.k + 1), 3),
    amplitude_mm: shown(Math.max(...h.s_m.map(Math.abs)) * 1000, 0),
    sigma_median_mm: shown(median(h.sigma_m) * 1000, 0),
    sigma_max_mm: shown(Math.max(...h.sigma_m) * 1000, 0),
    linear_sd: shown(linear, 4),
    mc_sd: shown(sd(draws), 4),
    mc_mean: shown(mean(draws), 4),
    full_ratio: shown(sd(draws) / linear, 2),
    mc_valid: draws.length,
    low_ratio: shown(low.ratio, 2),
    high_ratio: shown(high.ratio, 2),
    high_unresolved: high.unresolved,
    repro_cadence: cadenceHz(h.joints_s_m, h.fps).toFixed(4), // as the script prints it
    repro_sd: sd(repro).toFixed(4),
    repro_valid: repro.length,
  };
}

// Per match: the players over the protocol's floor in the fast band, their cadences and sds.
export function matchFigures(rows: readonly PlayerRow[]) {
  const cad = rows.map((r) => r.cadence_hz);
  const sds = rows.map((r) => r.sd_hz);
  return {
    players: rows.length,
    windows: rows.reduce((a, r) => a + r.finite_s, 0),
    cadence_min: Math.min(...cad),
    cadence_max: Math.max(...cad),
    sd_median: shown(median(sds), 4),
    sd_min: Math.min(...sds),
    sd_max: Math.max(...sds),
  };
}

export function cadenceFigures(hooks: readonly HookWindow[], fast: Readonly<Record<string, readonly PlayerRow[]>>) {
  const [first] = hooks;
  return {
    band_z: BAND_Z,
    draws: DRAWS,
    seed: SEED,
    scale_low: SCALE_LOW,
    scale_high: SCALE_HIGH,
    bin_hz: first.fps / first.s_m.length,
    bin_steps: (2 * first.fps) / first.s_m.length,
    hook: Object.fromEntries(hooks.map((h) => [h.match_id, windowFigures(h)])),
    match: Object.fromEntries(Object.entries(fast).map(([m, rows]) => [m, matchFigures(rows)])),
  };
}

export type CadenceFigures = ReturnType<typeof cadenceFigures>;
