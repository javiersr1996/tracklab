// Every figure the text of lesson 12 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs are
// expected-points.json's counts and its per-team rows; every other figure is the file's own.
import { CLASSES, type ExpectedFile, type ExpectedSeason, type TeamRow, type ZoneClass } from "./expected-data";
import { plainMean, shares } from "./expected";
import { shown } from "./expose";

type Field = "mix" | "making";

const byClass = (f: (c: ZoneClass) => number) => Object.fromEntries(CLASSES.map((c) => [c, f(c)])) as Record<ZoneClass, number>;

// The lowest and the highest team of a field, the first in the file's order on a tie, and the
// width between them, from the values the tables print.
function extremes(teams: readonly TeamRow[], field: Field) {
  const lo = teams.reduce((a, t) => (t[field] < a[field] ? t : a), teams[0]);
  const hi = teams.reduce((a, t) => (t[field] > a[field] ? t : a), teams[0]);
  return { lo: lo[field], lo_code: lo.code, hi: hi[field], hi_code: hi.code, range: shown(hi[field] - lo[field], 3) };
}

export function seasonFigures(s: ExpectedSeason) {
  const mix = extremes(s.teams, "mix");
  const making = extremes(s.teams, "making");
  return {
    pct: byClass((c) => shown((100 * s.league[c].made) / s.league[c].n, 1)),
    value: byClass((c) => shown(s.league[c].pts / s.league[c].made, 0)),
    attempts: CLASSES.reduce((sum, c) => sum + s.league[c].n, 0),
    plain: shown(plainMean(s.league), 3),
    teams: s.teams.length,
    mix_lo: mix.lo,
    mix_lo_code: mix.lo_code,
    mix_hi: mix.hi,
    mix_hi_code: mix.hi_code,
    mix_range: mix.range,
    making_lo: making.lo,
    making_lo_code: making.lo_code,
    making_hi: making.hi,
    making_hi_code: making.hi_code,
    making_range: making.range,
    ratio: shown(making.range / mix.range, 1),
    making_pos: s.teams.filter((t) => t.making > 0).length,
  };
}

// The example of the text: the team with the most points per shot in the first season (the
// first in the file's order on a tie), and its share of attempts in each class.
export function exampleTeam(s: ExpectedSeason) {
  const t = s.teams.reduce((a, x) => (x.pps > a.pps ? x : a), s.teams[0]);
  const sh = shares(t);
  return { season: s.season, code: t.code, share: byClass((c) => shown(100 * sh[c], 1)) };
}

// `learn.season.<season>.<key>` and `learn.ex.<key>`.
export function lessonExpectedFigures(file: ExpectedFile) {
  return {
    season: Object.fromEntries(file.seasons.map((s) => [s.season, seasonFigures(s)])) as Record<string, ReturnType<typeof seasonFigures>>,
    ex: exampleTeam(file.seasons[0]),
  };
}

export type ExpectedLessonFigures = ReturnType<typeof lessonExpectedFigures>;
