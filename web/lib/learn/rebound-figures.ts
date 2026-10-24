// Every figure the text of lesson 4 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are rebound.json's rows and its example, at the decimals it publishes.
import { shown } from "./expose";
import { argmin, arrival, chanceFirst, distance, nearest } from "./rebound";
import type { ReboundFile, ReboundMatch } from "./rebound-data";

// The reaction slider of the race figure: its range and step, in seconds.
export const REACTION_MAX = 1.5;
export const REACTION_STEP = 0.05;
// The top-speed slider, in m/s.
export const SPEED_MIN = 3;
export const SPEED_MAX = 9;
export const SPEED_STEP = 0.5;

const pct = (k: number, n: number) => shown((100 * k) / n, 0);
const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;
const sum = (m: readonly ReboundMatch[], f: (r: ReboundMatch) => number) => m.reduce((s, r) => s + f(r), 0);
export const steps = (lo: number, hi: number, step: number) => Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => Number((lo + i * step).toFixed(6)));

// The race at a reaction and a top speed: every time, the first, the nearest, the chances.
export function raceAt(file: ReboundFile, reaction: number, topSpeed: number) {
  const ex = file.example;
  const times = arrival(ex.players, ex.target, reaction, topSpeed);
  return { times, first: argmin(times), nearest: nearest(ex.players, ex.target), chance: chanceFirst(times, file.spread_s) };
}

// The smallest reaction on the slider at which the model's first is no longer the nearest player.
export function switchReaction(file: ReboundFile, topSpeed: number): number | null {
  const near = nearest(file.example.players, file.example.target);
  return steps(0, REACTION_MAX, REACTION_STEP).find((r) => raceAt(file, r, topSpeed).first !== near) ?? null;
}

// The reaction with the most hits in a match; the first on a tie.
export const peakReaction = (file: ReboundFile, m: ReboundMatch) => file.reactions[m.by_reaction.indexOf(Math.max(...m.by_reaction))];

export function reboundFigures(file: ReboundFile) {
  const ex = file.example;
  const at = raceAt(file, file.reaction_s, file.top_speed);
  const reb = ex.players[ex.rebounder];
  const near = ex.players[at.nearest];
  const second = argmin(at.times.map((t, i) => (i === at.first ? Infinity : t)));
  const sw = switchReaction(file, file.top_speed);

  const m = file.matches;
  const rate = Object.fromEntries(
    m.map((r) => [
      r.match_id,
      {
        model: pct(r.model, r.n),
        nearest: pct(r.nearest, r.n),
        same: pct(r.same, r.n),
        confidence: shown(100 * (r.confidence ?? NaN), 0),
      },
    ]),
  );
  const rates = Object.values(rate);
  const [modelLo, modelHi] = range(rates.map((r) => r.model));
  const [nearLo, nearHi] = range(rates.map((r) => r.nearest));
  const [sameLo, sameHi] = range(rates.map((r) => r.same));
  const [confLo, confHi] = range(rates.map((r) => r.confidence));
  const [waitLo, waitHi] = range(m.map((r) => r.median_wait_s ?? NaN));
  const [nLo, nHi] = range(m.map((r) => r.n));
  const [diffLo, diffHi] = range(m.map((r) => r.model - r.nearest));
  const peaks = m.map((r) => peakReaction(file, r));
  const [peakLo, peakHi] = range(peaks);
  const zero = file.reactions.indexOf(0);

  return {
    // The example, at the sources' reaction and top speed.
    ex_players: ex.players.length,
    ex_near_dist: shown(distance(near, ex.target), 2),
    ex_reb_dist: shown(distance(reb, ex.target), 2),
    ex_reb_speed: shown(Math.hypot(reb.vx, reb.vy), 2),
    ex_near_speed: shown(Math.hypot(near.vx, near.vy), 2),
    ex_reb_carry: shown(Math.hypot(reb.vx, reb.vy) * file.reaction_s, 2),
    ex_first_time: shown(at.times[at.first], 2),
    ex_near_time: shown(at.times[at.nearest], 2),
    ex_second_time: shown(at.times[second], 2),
    ex_first_chance: shown(100 * at.chance[at.first], 0),
    ex_near_chance: shown(100 * at.chance[at.nearest], 0),
    ex_second_chance: shown(100 * at.chance[second], 0),
    ex_gap_ms: shown(1000 * (at.times[second] - at.times[at.first]), 0),
    ex_switch_reaction: sw,
    // Every match.
    matches: m.length,
    rate,
    model_lo: modelLo,
    model_hi: modelHi,
    near_lo: nearLo,
    near_hi: nearHi,
    same_lo: sameLo,
    same_hi: sameHi,
    conf_lo: confLo,
    conf_hi: confHi,
    wait_lo: waitLo,
    wait_hi: waitHi,
    n_lo: nLo,
    n_hi: nHi,
    ahead: m.filter((r) => r.model > r.nearest).length,
    level: m.filter((r) => r.model === r.nearest).length,
    behind: m.filter((r) => r.model < r.nearest).length,
    diff_lo: diffLo,
    diff_hi: diffHi,
    conf_above: m.filter((r) => (r.confidence ?? NaN) > r.model / r.n).length,
    zero_is_nearest: m.filter((r) => r.by_reaction[zero] === r.nearest).length,
    peak_lo: peakLo,
    peak_hi: peakHi,
    // The selection, summed over the matches.
    rebounds: sum(m, (r) => r.rebounds),
    team_rebounds: sum(m, (r) => r.rebounds - r.by_player),
    not_field_goal: sum(m, (r) => r.by_player - r.field_goal),
    no_location: sum(m, (r) => r.field_goal - r.located),
    not_after: sum(m, (r) => r.located - r.after_end),
    not_ten: sum(m, (r) => r.after_end - r.n),
    raced: sum(m, (r) => r.n),
  };
}

export type ReboundFigures = ReturnType<typeof reboundFigures>;
