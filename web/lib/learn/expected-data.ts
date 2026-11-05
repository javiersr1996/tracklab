// Lesson 12's data, read at build time: `public/data/euroleague/expected-points.json`, written by
// `tracklab euroleague publish` with the atlas (task 117). Only counts by zone class and the points
// per shot they give; no shot. Only the server imports this file.
import expectedJson from "../../public/data/euroleague/expected-points.json";

export const CLASSES = ["rim", "mid", "three"] as const;
export type ZoneClass = (typeof CLASSES)[number];

export interface Tally {
  n: number;
  made: number;
  pts: number;
}

export type Zones = Record<ZoneClass, Tally>;

export interface TeamRow extends Zones {
  code: string;
  name: string;
  pps: number;
  xpps: number;
  mix: number;
  making: number;
  mix_ci: [number, number];
  making_ci: [number, number];
}

// How many times as wide a bootstrap over whole games makes a season's intervals (task 117b):
// median, min and max over its teams.
export interface Spread {
  median: number;
  min: number;
  max: number;
}

export interface ExpectedSeason {
  season: string;
  cutoff: string;
  games_played: number;
  league: Zones & { unclassified: number };
  pps: Record<ZoneClass, number>;
  mean: number;
  games_ratio: { mix: Spread; making: Spread } | null;
  teams: TeamRow[];
  teams_left_out: number;
}

export interface ExpectedFile {
  version: number;
  source: string;
  k: number;
  level: number;
  z: number;
  games_bootstrap: { seed: number; replicates: number };
  classes: string[];
  rim_zones: string[];
  seasons: ExpectedSeason[];
}

export const EXPECTED = expectedJson as unknown as ExpectedFile;

// The value a `data-fig` names in the file: `xp.<season>.<path>` is a path in that season's block,
// where the part after `teams` is a team code (`xp.E2025.teams.MAD.making`); `xp.<path>` with no
// season is a path from the file's root (`xp.rim_zones.0`). The e2e resolves names the same way.
export function xpFigure(file: ExpectedFile, name: string): unknown {
  const [prefix, first, ...rest] = name.split(".");
  if (prefix !== "xp" || first === undefined) return undefined;
  const block = file.seasons.find((s) => s.season === first);
  let at: unknown = block ?? (file as unknown as Record<string, unknown>)[first];
  for (let i = 0; i < rest.length; i++) {
    if (Array.isArray(at) && rest[i - 1] === "teams") at = at.find((t: TeamRow) => t.code === rest[i]);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[rest[i]] : undefined;
  }
  return at;
}

export const xpName = (season: string, path: string) => `xp.${season}.${path}`;
