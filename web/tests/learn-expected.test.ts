import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Lesson } from "../components/learn/expected/Lesson";
import { PerTeam } from "../components/learn/expected/PerTeam";
import { ZoneBars } from "../components/learn/expected/ZoneBars";
import { INK } from "../components/learn/gravity/Plot";
import { display } from "../lib/learn/display";
import { CLASSES, EXPECTED, type ExpectedFile, type ExpectedSeason, type TeamRow, type Zones, xpFigure } from "../lib/learn/expected-data";
import { excludesZero, lessonExpectedFigures, seasonFigures } from "../lib/learn/expected-figures";
import { intervals, plainMean, shares, split, weightedMean } from "../lib/learn/expected";
import { shown } from "../lib/learn/expose";

// Lesson 12 (task 117). The arithmetic is checked on counts worked out by hand (the same season as
// pipeline/tests/unit/test_euroleague_expected.py) and against every row the pipeline published;
// the text, as the server renders it, prints every figure as its source has it.
//
// Mutations checked by hand, each restored byte for byte:
// - making as xpps - pps in `split`: "a team against the league" and "every row" fail.
// - `weightedMean` as the plain mean of the classes: "the league's mean" and "every row" fail.
// - xpps as the plain mean of the league's classes (not weighted by the team's attempts):
//   "a team against the league" and "every row" fail.
// Task 117b, the intervals: centred on the league (0) instead of the team, z typed instead of the
// file's, making's centre with its sign flipped, and `>=` for "excludes zero": see todo.md.

const T = (n: number, made: number, pts: number) => ({ n, made, pts });
// AAA, BBB and the league (CCC's shots included) of the pipeline's hand-made season.
const AAA: Zones = { rim: T(10, 6, 12), mid: T(5, 2, 4), three: T(5, 2, 6) };
const BBB: Zones = { rim: T(10, 5, 10), mid: T(10, 5, 10), three: T(5, 3, 9) };
const LEAGUE: Zones = { rim: T(25, 15, 30), mid: T(20, 8, 16), three: T(14, 7, 21) };

const r3 = (x: number) => shown(x, 3);

describe("expected points on counts worked out by hand", () => {
  it("the league's mean is weighted by attempts, not the plain mean of its classes", () => {
    expect(weightedMean(LEAGUE)).toBeCloseTo(67 / 59, 12);
    expect(plainMean(LEAGUE)).toBeCloseTo(3.5 / 3, 12);
  });

  it("a team against the league: pps, xpps, mix and making", () => {
    expect(Object.values(split(AAA, LEAGUE)).map(r3)).toEqual([1.1, 1.175, 0.039, -0.075]);
    expect(Object.values(split(BBB, LEAGUE)).map(r3)).toEqual([1.16, 1.1, -0.036, 0.06]);
    const s = split(AAA, LEAGUE);
    expect(s.mix + s.making).toBeCloseTo(s.pps - 67 / 59, 12);
  });

  it("shares of attempts", () => {
    expect(shares(AAA)).toEqual({ rim: 0.5, mid: 0.25, three: 0.25 });
  });

  // pipeline/tests/unit/test_euroleague_expected.py works these out by hand in its docstring.
  it("the intervals of mix and making, plus and minus 1.96 standard errors", () => {
    const a = intervals(AAA, LEAGUE, 1.96);
    expect([...a.mix, ...a.making].map(r3)).toEqual([-0.07, 0.148, -0.57, 0.42]);
    const b = intervals(BBB, LEAGUE, 1.96);
    expect([...b.mix, ...b.making].map(r3)).toEqual([-0.141, 0.07, -0.383, 0.503]);
    // Centred on the team's own figure: 0.0394068 for AAA's mix, -0.075 for its making.
    expect((a.mix[0] + a.mix[1]) / 2).toBeCloseTo(1.175 - 67 / 59, 12);
    expect((a.making[0] + a.making[1]) / 2).toBeCloseTo(-0.075, 12);
    // Half as wide at half the z.
    const half = intervals(AAA, LEAGUE, 0.98);
    expect(half.making[1] - half.making[0]).toBeCloseTo((a.making[1] - a.making[0]) / 2, 12);
  });
});

describe("expected-points.json", () => {
  it("every row the pipeline wrote is what this arithmetic gives from the counts", () => {
    let rows = 0;
    for (const s of EXPECTED.seasons) {
      expect(CLASSES.map((c) => r3(s.league[c].pts / s.league[c].n))).toEqual(CLASSES.map((c) => s.pps[c]));
      expect(r3(weightedMean(s.league))).toBe(s.mean);
      for (const t of s.teams) {
        const got = split(t, s.league);
        expect([got.pps, got.xpps, got.mix, got.making].map(r3), `${s.season} ${t.code}`).toEqual([t.pps, t.xpps, t.mix, t.making]);
        rows++;
      }
    }
    expect(rows).toBeGreaterThanOrEqual(40);
  });

  it("every interval the pipeline wrote is what this arithmetic gives from the counts and the file's z", () => {
    expect([EXPECTED.level, EXPECTED.z]).toEqual([0.95, 1.96]);
    let rows = 0;
    for (const s of EXPECTED.seasons) {
      for (const t of s.teams) {
        const got = intervals(t, s.league, EXPECTED.z);
        expect([...got.mix, ...got.making].map(r3), `${s.season} ${t.code}`).toEqual([...t.mix_ci, ...t.making_ci]);
        rows++;
      }
    }
    expect(rows).toBeGreaterThanOrEqual(40);
  });

  it("the claims the text makes about the first season hold in the file", () => {
    const f = seasonFigures(EXPECTED.seasons[0], EXPECTED.level, EXPECTED.z);
    // More making intervals exclude zero than chance alone would give; most mix ones do, most making ones do not.
    expect(f.excl_making).toBeGreaterThan(f.chance);
    expect(f.excl_mix).toBeGreaterThan(f.teams / 2);
    expect(f.excl_making).toBeLessThan(f.teams / 2);
    expect(f.width_ratio).toBeGreaterThan(f.ratio);
  });

  // Task B3 of the P14b review: the count is on the unrounded bounds, and the printed ones give a
  // different count in a season (a bound printed 0 that is just above it). Mutation checked by
  // hand: counting on `mix_ci` and `making_ci` again fails this.
  it("counts the intervals that exclude zero on their unrounded bounds, not the printed ones", () => {
    let differ = 0;
    for (const s of EXPECTED.seasons) {
      const f = seasonFigures(s, EXPECTED.level, EXPECTED.z);
      const exact = s.teams.map((t) => intervals(t, s.league, EXPECTED.z));
      const side = ([lo, hi]: number[]) => lo > 0 || hi < 0;
      expect([f.excl_mix, f.excl_making]).toEqual([exact.filter((e) => side(e.mix)).length, exact.filter((e) => side(e.making)).length]);
      const printed = [s.teams.filter((t) => side(t.mix_ci)).length, s.teams.filter((t) => side(t.making_ci)).length];
      if (printed[0] !== f.excl_mix || printed[1] !== f.excl_making) differ++;
    }
    expect(differ).toBeGreaterThan(0);
  });

  it("resolves a figure's name to the file's value", () => {
    const [a] = EXPECTED.seasons;
    const t = a.teams[0];
    expect(xpFigure(EXPECTED, `xp.${a.season}.mean`)).toBe(a.mean);
    expect(xpFigure(EXPECTED, `xp.${a.season}.pps.rim`)).toBe(a.pps.rim);
    expect(xpFigure(EXPECTED, `xp.${a.season}.teams.${t.code}.making`)).toBe(t.making);
    expect(xpFigure(EXPECTED, `xp.${a.season}.league.mid.n`)).toBe(a.league.mid.n);
    expect(xpFigure(EXPECTED, "xp.rim_zones.1")).toBe(EXPECTED.rim_zones[1]);
    expect(xpFigure(EXPECTED, "xp.k")).toBe(EXPECTED.k);
    expect(xpFigure(EXPECTED, `xp.${a.season}.teams.ZZZ.making`)).toBeUndefined();
  });
});

// A season of three teams with figures chosen to tie and to cross zero.
const row = (code: string, pps: number, mix: number, making: number, mix_ci: [number, number], making_ci: [number, number]): TeamRow => ({
  code,
  name: code,
  ...AAA,
  pps,
  xpps: 0,
  mix,
  making,
  mix_ci,
  making_ci,
});
const spread = (median: number) => ({ median, min: median, max: median });
const SEASON: ExpectedSeason = {
  season: "E2025",
  cutoff: "2026-05-24",
  games_played: 3,
  league: { ...LEAGUE, unclassified: 0 },
  pps: { rim: 1.2, mid: 0.8, three: 1.5 },
  mean: 1.136,
  // AAA's mix interval starts at 0: it does not exclude zero.
  games_ratio: { mix: spread(1.2), making: spread(1) },
  teams: [
    row("AAA", 1.1, 0.02, -0.03, [0, 0.04], [-0.1, 0.04]),
    row("BBB", 1.2, -0.01, 0.07, [-0.02, -0.001], [0.01, 0.13]),
    row("CCC", 1.2, 0.02, 0.0, [0.005, 0.035], [-0.08, 0.08]),
  ],
  teams_left_out: 0,
};

describe("the figures the text computes", () => {
  it("extremes with their teams (the first on a tie), ranges and their ratio", () => {
    expect(seasonFigures(SEASON, 0.9, 1.645)).toEqual({
      pct: { rim: 60, mid: 40, three: 50 },
      value: { rim: 2, mid: 2, three: 3 },
      attempts: 59,
      plain: 1.167,
      teams: 3,
      mix_lo: -0.01,
      mix_lo_code: "BBB",
      mix_hi: 0.02,
      mix_hi_code: "AAA",
      mix_range: 0.03,
      making_lo: -0.03,
      making_lo_code: "AAA",
      making_hi: 0.07,
      making_hi_code: "BBB",
      making_range: 0.1,
      ratio: 3.3,
      making_pos: 1, // zero is not above
      excl_mix: 0, // the three teams have AAA's counts: the bounds are from them, not the rows' intervals
      excl_making: 0,
      chance: 0.3, // (1 - 0.9) * 3
      width_ratio: 4.7, // making's median width 0.14 over mix's 0.03
      wide_mix: 1, // at 1.2 times as wide, only CCC's (0.02 > 1.2 * 0.015); BBB's would at 1
    });
  });

  it("an interval excludes zero only with both bounds on one side of it", () => {
    expect([[0.001, 0.2], [-0.2, -0.001], [0, 0.2], [-0.2, 0], [-0.1, 0.1]].map((ci) => excludesZero(ci as [number, number]))).toEqual([
      true,
      true,
      false,
      false,
      false,
    ]);
    expect(seasonFigures({ ...SEASON, games_ratio: { mix: spread(1), making: spread(1) } }, 0.9, 1.645).wide_mix).toBe(2);
  });

  it("the example is the team with the most points per shot of the first season", () => {
    const file: ExpectedFile = { ...EXPECTED, seasons: [SEASON] };
    expect(lessonExpectedFigures(file).ex).toMatchObject({ season: "E2025", code: "BBB", share: { rim: 50, mid: 25, three: 25 } });
    expect(lessonExpectedFigures(file).level_pct).toBe(95);
  });

  // The guided sentence subtracts the figures it prints, so its sum adds up even where the file's
  // mix, which subtracts before it rounds, is a thousandth off. Mutation checked by hand: taking
  // the file's mix and making for the example's (as before) fails the second test, on HTA.
  it("the example's mix and making are the subtraction of the figures the text prints", () => {
    const [first] = EXPECTED.seasons;
    const ex = lessonExpectedFigures(EXPECTED).ex;
    const t = first.teams.find((x) => x.code === ex.code)!;
    expect(ex.mix).toBe(shown(t.xpps - first.mean, 3));
    expect(ex.making).toBe(shown(t.pps - t.xpps, 3));
  });
});

// The text and the figures as the server renders them.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "expected-points.sql"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: SQL }));
const F = lessonExpectedFigures(EXPECTED);
const LEVEL = { z: EXPECTED.z, pct: F.level_pct };
const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const get = (root: unknown, path: string) =>
  path.split(".").reduce<unknown>((o, k) => (o !== null && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), root);

describe("the text of lesson 12", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(150);
    const wrong = figs.filter(([name, text]) => {
      const value = name.startsWith("learn.") ? get(F, name.slice(6)) : xpFigure(EXPECTED, name);
      return value === undefined || text !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("types no digit outside figures, seasons, formulas, quotes, code, tables and the contact address", () => {
    const prose = entities(
      HTML.replace(/<span data-(?:fig|series-n|season)="[^"]*">[^<]*<\/span>/g, " ")
        .replace(/<(figure|pre|math|table|cite|q|code|textarea)[\s>][\s\S]*?<\/\1>/g, " ")
        .replace(/<a href="mailto:[^"]*">[^<]*<\/a>/g, " ")
        .replace(/<[^>]+>/g, " "),
    );
    expect(prose.match(/.{0,30}\d+.{0,30}/g) ?? []).toEqual([]);
  });

  it("shows a mix and a making that add up from the figures printed beside them", () => {
    const [first] = EXPECTED.seasons;
    const t = first.teams.find((x) => x.code === F.ex.code)!;
    const text = entities(HTML.replace(/<[^>]+>/g, ""));
    const m = (v: number) => display(String(v), "learn.ex.mix");
    expect(text).toContain(`${t.xpps} minus ${first.mean}, is ${m(F.ex.mix)}`);
    expect(Math.abs(t.xpps - first.mean - F.ex.mix)).toBeLessThan(1e-9);
  });

  it("names its source and says it is not affiliated", () => {
    expect(HTML).toContain(`data-attribution="source">Data: <a href="https://www.euroleaguebasketball.net/euroleague/">${EXPECTED.source}</a>`);
    expect(HTML).toContain('data-attribution="affiliation">Not affiliated with EuroLeague.</p>');
  });
});

describe("the figures", () => {
  it("draw every mark in a colour of the lessons' palette", () => {
    const markup = [renderToStaticMarkup(createElement(ZoneBars, { seasons: EXPECTED.seasons })), renderToStaticMarkup(createElement(PerTeam, { seasons: EXPECTED.seasons, level: LEVEL }))].join("");
    const colours = new Set([...markup.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((m) => m[1]).filter((c) => c !== "none"));
    expect([...colours].filter((c) => !Object.values(INK).includes(c as (typeof INK)[keyof typeof INK]))).toEqual([]);
  });

  it("list every team of each season, the most points per shot first", () => {
    const markup = renderToStaticMarkup(createElement(PerTeam, { seasons: EXPECTED.seasons, level: LEVEL }));
    for (const s of EXPECTED.seasons) {
      const table = markup.match(new RegExp(`<table[^>]*data-season="${s.season}"[\\s\\S]*?</table>`))![0];
      const order = [...table.matchAll(/data-team="([A-Z0-9]+)"/g)].map((m) => m[1]);
      const pps = order.map((code) => s.teams.find((t) => t.code === code)!.pps);
      expect([...order].sort()).toEqual(s.teams.map((t) => t.code).sort());
      expect(pps).toEqual([...pps].sort((a, b) => b - a));
    }
  });
});
