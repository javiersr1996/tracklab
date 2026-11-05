// The shape of public/data/euroleague/runs.json (task 118): the top of each season's biggest runs and
// comebacks, and a summary by team. Scores are [the team's, the rival's].
export type Pair = [number, number];

export interface RunRow {
  team: string;
  opp: string;
  date: string;
  size: number;
  from: Pair;
  to: Pair;
}

export interface ComebackRow {
  team: string;
  opp: string;
  date: string;
  deficit: number;
  at: Pair;
  final: Pair;
}

export interface TeamRuns {
  code: string;
  games: number;
  best_run: number;
  runs_n: number;
  comeback_for: number;
  comeback_against: number;
  wins_from_n: number;
}

export interface RunsSeason {
  season: string;
  cutoff: string;
  games_played: number;
  games_read: number;
  games_left_out: number;
  runs: RunRow[];
  comebacks: ComebackRow[];
  teams: TeamRuns[];
}

export interface Runs {
  version: number;
  source: string;
  top: number;
  run_min: number;
  deficit_min: number;
  seasons: RunsSeason[];
}

// "Competition" rank of each size in a list sorted from the biggest: 25, 22, 18, 18, 17 is 1, 2, 3, 3, 5.
export function ranks(sizes: readonly number[]): number[] {
  return sizes.map((s) => 1 + sizes.filter((o) => o > s).length);
}

export const score = ([own, rival]: Pair): string => `${own}–${rival}`;
