// `web/public/data/quality.json` (task 30), read at build time like `stats.json`
// in `lib/data.ts`: every figure on `/engineering/quality` is the one this file was built with.
import quality from "../public/data/quality.json";

export interface QualityRow {
  sport: string;
  match_id: string;
  metric: string;
  value: number;
  unit: string;
  n: number;
}

export interface Hook {
  match_id: string;
  shot_id: string;
  start_frame: number;
  g_data: number;
  g_real: number;
  median_calibration_g: number;
  t_s: number[];
  z_data_m: number[];
  z_real_m: number[];
}

export interface QualityData {
  schema_version: number;
  checks: Record<string, QualityRow[]>;
  summary: { ranges: Record<string, string> } & Record<string, unknown>;
  hook: Hook;
}

const DATA = quality as QualityData;

export const QUALITY: QualityData = DATA;
export const CHECKS = DATA.checks;
export const HOOK = DATA.hook;

export interface TableMetric {
  check: string;
  metric: string;
  label: string;
  unit: string;
}

// The metrics the per-match table shows, one column each; a match missing a
// metric (e.g. football has no entry_angle) renders that cell empty.
export const TABLE_METRICS: TableMetric[] = [
  { check: "detection", metric: "ball_detected_pct", label: "Ball detected", unit: "%" },
  { check: "detection", metric: "player_detected_pct", label: "Player detected", unit: "%" },
  { check: "gravity", metric: "g_median", label: "Median g", unit: "m/s²" },
  { check: "gravity", metric: "g_median_bias_pct", label: "g bias", unit: "%" },
  { check: "entry_angle", metric: "gap_median_deg", label: "Entry angle gap", unit: "°" },
  { check: "noise", metric: "ball_player_d2_ratio", label: "Ball/player jitter", unit: "×" },
  { check: "clock", metric: "clock_step_exact_pct", label: "Clock step exact", unit: "%" },
];

export interface MatchRow {
  sport: string;
  match_id: string;
  cells: Record<string, number | undefined>;
}

export const cellKey = (check: string, metric: string): string => `${check}.${metric}`;

// One row per (sport, match): every check's kept metrics pivoted onto it.
export function matchRows(): MatchRow[] {
  const bySport = new Map<string, MatchRow>();
  for (const [check, rows] of Object.entries(CHECKS)) {
    for (const row of rows) {
      const key = `${row.sport}|${row.match_id}`;
      let entry = bySport.get(key);
      if (!entry) {
        entry = { sport: row.sport, match_id: row.match_id, cells: {} };
        bySport.set(key, entry);
      }
      entry.cells[cellKey(check, row.metric)] = row.value;
    }
  }
  return [...bySport.values()].sort((a, b) =>
    a.sport === b.sport ? a.match_id.localeCompare(b.match_id) : a.sport.localeCompare(b.sport),
  );
}
