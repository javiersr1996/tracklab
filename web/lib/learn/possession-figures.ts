// Every figure the text of lesson 10 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are possession.json's per-match rows and its two timelines; basketball's game-clock figures are
// the rows' own, read as they are.
import { shown } from "./expose";
import { expRatio, expSurvival, quantile, survival } from "./possession";
import { durations, spells, type PossessionFile, type Timeline } from "./possession-data";

const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;

// One example match, from its timeline: how long its units last and how their tail compares with
// an exponential of the same median.
export function timelineFigures(t: Timeline) {
  const s = spells(t);
  const d = durations(s);
  const median = quantile(d, 0.5);
  const p90 = quantile(d, 0.9);
  const longest = s.reduce((best, x) => (x.end - x.start > best.end - best.start ? x : best), s[0]);
  return {
    n: d.length,
    median: shown(median, 2),
    p90: shown(p90, 2),
    ratio: shown(p90 / median, 2),
    beyond2_pct: shown(100 * survival(d, 2 * median), 1),
    beyond4_pct: shown(100 * survival(d, 4 * median), 1),
    exp_beyond2_pct: shown(100 * expSurvival(median, 2 * median), 1),
    exp_beyond4_pct: shown(100 * expSurvival(median, 4 * median), 2),
    shortest: shown(Math.min(...d), 2),
    longest: shown(longest.end - longest.start, 2),
    longest_phases: longest.phases,
    periods: new Set(s.map((x) => x.period)).size,
  };
}

export function lessonPossessionFigures(file: PossessionFile) {
  const fb = file.football.matches;
  const bb = file.basketball.matches;
  const exp = expRatio(0.9);
  const fbRatio = Object.fromEntries(fb.map((m) => [m.match_id, shown(m.run_p90_s / m.run_median_s, 2)]));
  const bbRatio = Object.fromEntries(bb.map((m) => [m.match_id, shown(m.p90_s / m.median_s, 2)]));
  const [fbMedLo, fbMedHi] = range(fb.map((m) => m.run_median_s));
  const [fbP90Lo, fbP90Hi] = range(fb.map((m) => m.run_p90_s));
  const [fbMultiLo, fbMultiHi] = range(fb.map((m) => m.multi_phase_pct));
  const [fbRunsLo, fbRunsHi] = range(fb.map((m) => m.runs));
  const [fbPhasesLo, fbPhasesHi] = range(fb.map((m) => m.phases));
  const [bbMedLo, bbMedHi] = range(bb.map((m) => m.median_s));
  const [bbP90Lo, bbP90Hi] = range(bb.map((m) => m.p90_s));
  const [bbNLo, bbNHi] = range(bb.map((m) => m.possessions));
  const [fbRLo, fbRHi] = range(Object.values(fbRatio));
  const [bbRLo, bbRHi] = range(Object.values(bbRatio));
  const [clkMedLo, clkMedHi] = range(bb.map((m) => m.clock_median_s));
  const [clkP90Lo, clkP90Hi] = range(bb.map((m) => m.clock_p90_s));
  const [clkRLo, clkRHi] = range(bb.map((m) => m.clock_p90_over_median));
  return {
    fb: timelineFigures(file.football.timeline),
    bb: timelineFigures(file.basketball.timeline),
    fb_ratio: fbRatio,
    bb_ratio: bbRatio,
    exp_ratio: shown(exp, 2),
    exp_beyond2_pct: shown(100 * expSurvival(1, 2), 0),
    fb_matches: fb.length,
    bb_matches: bb.length,
    fb_med_lo: fbMedLo,
    fb_med_hi: fbMedHi,
    fb_p90_lo: fbP90Lo,
    fb_p90_hi: fbP90Hi,
    fb_multi_lo: fbMultiLo,
    fb_multi_hi: fbMultiHi,
    fb_runs_lo: fbRunsLo,
    fb_runs_hi: fbRunsHi,
    fb_phases_lo: fbPhasesLo,
    fb_phases_hi: fbPhasesHi,
    fb_runs: fb.reduce((s, m) => s + m.runs, 0),
    fb_ratio_lo: fbRLo,
    fb_ratio_hi: fbRHi,
    fb_above: fb.filter((m) => fbRatio[m.match_id] > exp).length,
    bb_med_lo: bbMedLo,
    bb_med_hi: bbMedHi,
    bb_p90_lo: bbP90Lo,
    bb_p90_hi: bbP90Hi,
    bb_n_lo: bbNLo,
    bb_n_hi: bbNHi,
    bb_possessions: bb.reduce((s, m) => s + m.possessions, 0),
    bb_ratio_lo: bbRLo,
    bb_ratio_hi: bbRHi,
    bb_above: bb.filter((m) => bbRatio[m.match_id] > exp).length,
    bb_clk_med_lo: clkMedLo,
    bb_clk_med_hi: clkMedHi,
    bb_clk_p90_lo: clkP90Lo,
    bb_clk_p90_hi: clkP90Hi,
    bb_clk_ratio_lo: clkRLo,
    bb_clk_ratio_hi: clkRHi,
    bb_clk_missing: bb.reduce((s, m) => s + m.possessions - m.clock_possessions, 0),
  };
}

export type PossessionLessonFigures = ReturnType<typeof lessonPossessionFigures>;
