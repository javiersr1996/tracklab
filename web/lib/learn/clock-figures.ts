// Every figure the text of lesson 6 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are clock.json, its two published possessions and the hook of quality.json (lesson 1's g).
import { firstMove, fitLine, gInSeconds, residuals, rms, scaleForG, slopeForG, type LineFit } from "./clock";
import type { ClockExample, ClockFile, ClockMatch } from "./clock-data";
import { shown } from "./expose";

// The possessions write the clock at two decimals (`publish/possessions.py`, `ROUND_NDIGITS`).
export const CLOCK_UNIT_S = 0.01;
// The figure never fits fewer frames than this (one second).
export const MIN_FIT = 25;

const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;

// The fit of one example from frame `from` to its last: slope, residuals and their size, in ms.
export function fitFrom(ex: ClockExample, from: number) {
  const t = ex.t.slice(from);
  const y = ex.clock.slice(from);
  const fit: LineFit = fitLine(t, y);
  const res = residuals(t, y, fit).map((r) => 1000 * r);
  return { fit, t, res, rms_ms: rms(res), max_ms: Math.max(...res.map(Math.abs)) };
}

// Where the flag says the clock runs again after its last stop in the possession (0 if it never
// stops), and the last frame before the clock moves from there.
export function flagRuns(ex: ClockExample): number {
  return ex.stopped.length ? ex.stopped[ex.stopped.length - 1][1] + 1 : 0;
}
export const moves = (ex: ClockExample): number => firstMove(ex.clock, flagRuns(ex));

export const heldPct = (m: ClockMatch) => shown((100 * m.held) / m.steps, 1);

export function clockFigures(file: ClockFile, examples: readonly ClockExample[], g: number, G: number) {
  const cal = examples.find((e) => e.key === "calibration");
  const ctl = examples.find((e) => e.key === "control");
  if (!cal || !ctl) throw new Error("clock.json needs one calibration and one control example");
  const calAll = fitFrom(cal, 0);
  const ctlAll = fitFrom(ctl, 0);
  const ctlFlag = fitFrom(ctl, flagRuns(ctl));
  const ctlMove = fitFrom(ctl, moves(ctl));
  const [stop0, stop1] = ctl.stopped[ctl.stopped.length - 1];
  const fps = file.fps;

  const m = file.matches;
  const calM = m.filter((r) => r.calibration);
  const ctlM = m.filter((r) => !r.calibration);
  const [calLo, calHi] = range(calM.map((r) => r.slope_median));
  const [ctlLo, ctlHi] = range(ctlM.map((r) => r.slope_median));
  const [segLo, segHi] = range(m.map((r) => r.segments));
  const minutes = m.map((r) => r.frames / fps / 60);
  const [minLo, minHi] = range(minutes);
  const calDev = Math.max(...calM.map((r) => Math.abs(r.slope_median + 1)));
  const ctlFar = ctlM.reduce((far, r) => (Math.abs(r.slope_median + 1) > Math.abs(far + 1) ? r.slope_median : far), -1);
  const [heldLo, heldHi] = range(ctlM.map(heldPct));

  return {
    // The two possessions of the figure.
    cal_frames: cal.t.length,
    cal_seconds: shown(cal.t[cal.t.length - 1], 2),
    cal_slope: shown(calAll.fit.slope, 5),
    cal_rms_ms: shown(calAll.rms_ms, 1),
    cal_max_ms: shown(calAll.max_ms, 1),
    clock_unit_ms: shown(1000 * CLOCK_UNIT_S, 0),
    half_unit_ms: shown(500 * CLOCK_UNIT_S, 0),
    ctl_frames: ctl.t.length,
    ctl_stopped_s: shown((stop1 - stop0 + 1) / fps, 2),
    ctl_hold_frames: moves(ctl) - flagRuns(ctl),
    ctl_hold_s: shown((moves(ctl) - flagRuns(ctl)) / fps, 2),
    ctl_slope_all: shown(ctlAll.fit.slope, 5),
    ctl_rms_all_ms: shown(ctlAll.rms_ms, 0),
    ctl_slope_flag: shown(ctlFlag.fit.slope, 5),
    ctl_slope_move: shown(ctlMove.fit.slope, 5),
    ctl_rms_move_ms: shown(ctlMove.rms_ms, 1),
    min_fit: MIN_FIT,
    // Every match.
    matches: m.length,
    cal_n: calM.length,
    ctl_n: ctlM.length,
    min_seconds: file.min_frames / fps,
    seg_lo: segLo,
    seg_hi: segHi,
    segments: m.reduce((s, r) => s + r.segments, 0),
    minutes_lo: shown(minLo, 0),
    minutes_hi: shown(minHi, 0),
    cal_lo: calLo,
    cal_hi: calHi,
    ctl_lo: ctlLo,
    ctl_hi: ctlHi,
    cal_held: calM.reduce((s, r) => s + r.held, 0),
    ctl_held_lo: heldLo,
    ctl_held_hi: heldHi,
    held_pct: Object.fromEntries(m.map((r) => [r.match_id, heldPct(r)])),
    // What a scale on the video's clock would do to lesson 1's g.
    hook_g: g,
    slope_for_g: shown(slopeForG(g, G), 4),
    shrink_pct: shown(100 * (1 - scaleForG(g, G)), 1),
    need_g_pct: shown(100 * (G / g - 1), 1),
    cal_dev: shown(calDev, 5),
    cal_g_pct: shown(100 * (gInSeconds(g, 1 - calDev) / g - 1), 2),
    ctl_far: ctlFar,
    ctl_g_pct: shown(100 * (gInSeconds(g, -ctlFar) / g - 1), 1),
  };
}

export type ClockFigures = ReturnType<typeof clockFigures>;
