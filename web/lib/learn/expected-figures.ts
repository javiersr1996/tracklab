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

const median = (xs: readonly number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// An interval, as the file prints it, excludes 0 when both bounds are on one side of it: a bound
// at 0 does not.
export const excludesZero = ([lo, hi]: readonly [number, number]) => lo > 0 || hi < 0;
const width = ([lo, hi]: readonly [number, number]) => hi - lo;

// The conclusion of the intervals (task 117b): how many teams' mix and making exclude 0, how many
// would by chance alone at the file's level if no team differed from the league, how many times as
// wide making's intervals are as mix's (medians), and how many mix intervals still exclude 0 when
// widened, about the figure, by the median ratio of the bootstrap over games.
function intervalFigures(s: ExpectedSeason, level: number) {
  const factor = s.games_ratio?.mix.median ?? 1;
  return {
    excl_mix: s.teams.filter((t) => excludesZero(t.mix_ci)).length,
    excl_making: s.teams.filter((t) => excludesZero(t.making_ci)).length,
    chance: shown((1 - level) * s.teams.length, 1),
    width_ratio: shown(median(s.teams.map((t) => width(t.making_ci))) / median(s.teams.map((t) => width(t.mix_ci))), 1),
    wide_mix: s.teams.filter((t) => Math.abs(t.mix) > (factor * width(t.mix_ci)) / 2).length,
  };
}

export function seasonFigures(s: ExpectedSeason, level: number) {
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
    ...intervalFigures(s, level),
  };
}

// The example of the text: the team with the most points per shot in the first season (the
// first in the file's order on a tie), and its share of attempts in each class.
export function exampleTeam(s: ExpectedSeason) {
  const t = s.teams.reduce((a, x) => (x.pps > a.pps ? x : a), s.teams[0]);
  const sh = shares(t);
  return { season: s.season, code: t.code, share: byClass((c) => shown(100 * sh[c], 1)) };
}

// `learn.season.<season>.<key>`, `learn.ex.<key>` and `learn.level_pct`.
export function lessonExpectedFigures(file: ExpectedFile) {
  return {
    season: Object.fromEntries(file.seasons.map((s) => [s.season, seasonFigures(s, file.level)])) as Record<string, ReturnType<typeof seasonFigures>>,
    ex: exampleTeam(file.seasons[0]),
    level_pct: shown(100 * file.level, 0),
  };
}

export type ExpectedLessonFigures = ReturnType<typeof lessonExpectedFigures>;
