// Every figure the text of lesson 1 computes (task 80), rounded as it is printed: the page shows
// each as `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The
// inputs are the hook flight and the basketball rows of `quality.json`, plus P3's synthetic flight
// (`tests/unit/test_quality_flight.py`: 25 fps, the ±10 window cut from a ±20 track, apex 4 m).
import { shown } from "./expose";
import {
  analyticSdG,
  apparentG,
  countBelow,
  gAtHalfWindow,
  knotsEvery,
  movingAverage,
  parabolaTrack,
  residualsAt,
  rmsAt,
  roundingBound,
  signTest,
  timeScaleNeeded,
  heightScaleNeeded,
} from "./gravity";
import { HOOK_Z_HALF_UNIT_M, type GravityHook, type MatchGravity } from "./gravity-data";

const FPS = 25;
const MARGIN = 10;
const APEX_Z_M = 4;
const MOVING_AVERAGE_K = 5;
const KNOT_EVERY = 5;
const NOISE_SIGMA_MM = 10;
const H_MIN = 2;

export function lessonFigures(hook: GravityHook, matches: readonly MatchGravity[]) {
  const { t_s: t, z_data_m: z, g_real: G } = hook;
  const g = apparentG(t, z);
  const rms = rmsAt(t, z, g);
  const rmsG = rmsAt(t, z, G);
  const half = (t.length - 1) / 2;
  const byH = Array.from({ length: half - H_MIN + 1 }, (_, k) => ({ h: H_MIN + k, g: gAtHalfWindow(t, z, H_MIN + k) }));
  const highest = byH.reduce((best, r) => (r.g > best.g ? r : best));
  const sdAtRms = analyticSdG(t, rms);
  const sign = signTest(
    matches.map((m) => m.g_median),
    G,
  );

  const track = parabolaTrack(FPS, half + MARGIN, APEX_Z_M, G);
  const cut = (xs: readonly number[]) => xs.slice(MARGIN, xs.length - MARGIN);
  const knotBias = Array.from({ length: KNOT_EVERY }, (_, phase) => 100 * (apparentG(cut(track.t), cut(knotsEvery(track.z, KNOT_EVERY, phase))) / G - 1));

  return {
    samples: t.length,
    half_s: shown(t[t.length - 1], 2),
    window_h_p3: half,
    fit_g: shown(g, 5),
    fit_below_pct: shown(100 * (1 - g / G), 1),
    rounding_bound: shown(roundingBound(t, HOOK_Z_HALF_UNIT_M), 4),
    fit_rms_mm: shown(rms * 1000, 1),
    fit_max_mm: shown(Math.max(...residualsAt(t, z, g).map(Math.abs)) * 1000, 1),
    g_rms_mm: shown(rmsG * 1000, 1),
    rms_ratio: shown(rmsG / rms, 0),
    noise_sigma_mm: NOISE_SIGMA_MM,
    sd_at_sigma: shown(analyticSdG(t, NOISE_SIGMA_MM / 1000), 3),
    sd_at_rms: shown(sdAtRms, 3),
    gap_sd: shown((G - g) / sdAtRms, 0),
    window_g_max: shown(highest.g, 5),
    window_h_at_max: highest.h,
    window_g_shortest: shown(byH[0].g, 5),
    window_h_shortest: byH[0].h,
    matches: matches.length,
    medians_below: sign.k,
    sign_n: sign.n,
    sign_p: Number(sign.p.toPrecision(2)),
    q3_below: countBelow(
      matches.map((m) => m.g_q3),
      G,
    ),
    moving_average_k: MOVING_AVERAGE_K,
    moving_average_g: shown(apparentG(cut(track.t), cut(movingAverage(track.z, MOVING_AVERAGE_K))), 5),
    knot_every: KNOT_EVERY,
    knots_down_pct: shown(-Math.min(...knotBias), 2),
    knots_up_pct: shown(Math.max(...knotBias), 2),
    time_shrink_pct: shown(100 * timeScaleNeeded(g, G), 1),
    height_scale: shown(heightScaleNeeded(g, G), 3),
  };
}

export type LessonFigures = ReturnType<typeof lessonFigures>;
