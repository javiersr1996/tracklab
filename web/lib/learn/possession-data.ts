// Lesson 10's data, read at build time: `public/data/learn/possession.json` (`tracklab learn
// possession`). Football is only ever the matches outside the Analytics Cup fence's held-out list;
// the pipeline never reads the others. Only the server imports this file; the figure gets the two
// timelines as props.
import possessionJson from "../../public/data/learn/possession.json";

export interface FootballMatch {
  match_id: string;
  phases: number;
  runs: number;
  run_median_s: number;
  run_p90_s: number;
  multi_phase_pct: number;
}

export interface BasketballMatch {
  match_id: string;
  possessions: number;
  median_s: number;
  p90_s: number;
}

export interface Timeline {
  match_id: string;
  teams: number[];
  columns: string[];
  rows: number[][]; // [period, start_s, end_s, team index, (phases)]
}

export interface PossessionFile {
  schema_version: number;
  football_hz: number;
  basketball_fps: number;
  football: { matches: FootballMatch[]; timeline: Timeline };
  basketball: { matches: BasketballMatch[]; timeline: Timeline };
}

export const POSSESSION = possessionJson as PossessionFile;

// A timeline as the figure draws it: each unit's period, start and end (s) and team (0 or 1).
export interface Spell {
  period: number;
  start: number;
  end: number;
  team: number;
  phases: number;
}

export function spells(t: Timeline): Spell[] {
  const at = (name: string) => t.columns.indexOf(name);
  const [p, a, b, team, n] = ["period", "start_s", "end_s", "team", "phases"].map(at);
  return t.rows.map((r) => ({ period: r[p], start: r[a], end: r[b], team: r[team], phases: n < 0 ? 1 : r[n] }));
}

export const durations = (s: readonly Spell[]): number[] => s.map((x) => x.end - x.start);
