// The published EuroLeague aggregates, read at build time by /euroleague (task 116), like
// lib/platform.ts reads platform.json: the league file is imported, and of each team file only
// what the page prints without a click (its "what has changed" and how many players it has) is
// read here. A team's hexagons are fetched by the browser when that team is chosen.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import leagueJson from "../../public/data/euroleague/league.json";
import { CURRENT_SEASON, type League, type Team, type TeamChanges } from "./atlas";

export const LEAGUE = leagueJson as unknown as League;

const TEAMS_DIR = join(process.cwd(), "public", "data", "euroleague", "teams");

function readTeams(): Team[] {
  return readdirSync(TEAMS_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => JSON.parse(readFileSync(join(TEAMS_DIR, f), "utf-8")) as Team);
}

export interface TeamsSummary {
  changes: TeamChanges[];
  // The minimum a player needs for his own hexagons (each team file's `player_min_shots`).
  playerMinShots: number;
  // Players who have reached it in the season still being played, over all teams.
  playersNow: number;
}

export function teamsSummary(): TeamsSummary {
  const teams = readTeams();
  const mins = new Set(teams.map((t) => t.player_min_shots));
  if (mins.size !== 1) throw new Error(`team files disagree on player_min_shots: ${[...mins].join(", ")}`);
  return {
    changes: teams.map((t) => ({ code: t.code, name: t.name, changes: t.changes })),
    playerMinShots: [...mins][0],
    playersNow: teams.reduce(
      (sum, t) => sum + (t.seasons.find((s) => s.season === CURRENT_SEASON)?.players.length ?? 0),
      0,
    ),
  };
}

// The share of a season's field goals that were three-point attempts, in % to one decimal.
export function threeShare(season: League["seasons"][number]): number {
  return Math.round((season.zones.three.n / season.shots_total) * 1000) / 10;
}
