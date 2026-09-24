// The two published summaries (task 17). Imported, not fetched: pages render their
// figures at build time, so every number on them is the one in the file.
import index from "../public/data/index.json";
import stats from "../public/data/stats.json";
import type { Sport } from "./replay/types";

export interface IndexEntry {
  possession_id: string;
  sport: Sport;
  match_id: string;
  home: string;
  away: string;
  duration_s: number;
  sample_rate_hz: number;
  file: string;
  bytes: number;
}

export const POSSESSIONS = index.possessions as IndexEntry[];

export const SPORTS: Sport[] = ["basketball", "football"];

// Rows of one silver table for one sport, summed over its matches.
export function rowsOf(table: string, sport: Sport): number {
  return stats.tables
    .filter((row) => row.table === table && row.sport === sport)
    .reduce((sum, row) => sum + row.rows, 0);
}
