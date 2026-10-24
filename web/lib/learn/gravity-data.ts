// Lesson 1's slice of `quality.json` (P3, task 30), read at build time through `lib/quality.ts`:
// the basketball rows of the gravity check, pivoted to one per match, and the hook flight. Football
// stays out (its g filters on `is_detected`, and half of its matches are held out by `fence.json`).
// Every figure here is the file's; nothing is recomputed.
import { CHECKS, HOOK, type Hook, type QualityRow } from "../quality";

export interface MatchGravity {
  match_id: string;
  flights: number;
  g_median: number;
  g_q1: number;
  g_q3: number;
  is_calibration: boolean;
}

export type GravityHook = Pick<
  Hook,
  "match_id" | "shot_id" | "g_data" | "g_real" | "t_s" | "z_data_m" | "z_real_m"
>;

// The hook's `z_data_m` and `z_real_m` are written at 4 decimals (`publish/quality.py:327` and
// `:350`), so each sample is within half a unit of the fourth of its value: `roundingBound`'s input.
export const HOOK_Z_HALF_UNIT_M = 0.00005;

export function basketballGravity(rows: readonly QualityRow[]): MatchGravity[] {
  const byMatch = new Map<string, Map<string, number>>();
  for (const row of rows) {
    if (row.sport !== "basketball") continue;
    const metrics = byMatch.get(row.match_id) ?? new Map<string, number>();
    metrics.set(row.metric, row.value);
    byMatch.set(row.match_id, metrics);
  }
  return [...byMatch].map(([match_id, metrics]) => {
    const value = (metric: string): number => {
      const v = metrics.get(metric);
      if (v === undefined) throw new Error(`quality.json has no gravity ${metric} for ${match_id}`);
      return v;
    };
    return {
      match_id,
      flights: value("flights"),
      g_median: value("g_median"),
      g_q1: value("g_q1"),
      g_q3: value("g_q3"),
      is_calibration: value("is_calibration") === 1,
    };
  });
}

export const GRAVITY_MATCHES = basketballGravity(CHECKS.gravity);

// The `data-fig` path of one figure of the file. Paths are dotted keys into `quality.json`,
// except that under `checks.<check>` the next two parts are a match id and a metric, the way the
// file keys its rows: `checks.gravity.bb:114086.g_median` is the `value` of that row.
export const gravityFig = (match_id: string, metric: string): string => `checks.gravity.${match_id}.${metric}`;

export function qualityFigure(data: unknown, path: string): unknown {
  const parts = path.split(".");
  if (parts[0] === "checks" && parts.length === 4) {
    const rows = (data as { checks?: Record<string, QualityRow[]> }).checks?.[parts[1]];
    return rows?.find((r) => r.match_id === parts[2] && r.metric === parts[3])?.value;
  }
  return parts.reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), data);
}

export const GRAVITY_HOOK: GravityHook = {
  match_id: HOOK.match_id,
  shot_id: HOOK.shot_id,
  g_data: HOOK.g_data,
  g_real: HOOK.g_real,
  t_s: HOOK.t_s,
  z_data_m: HOOK.z_data_m,
  z_real_m: HOOK.z_real_m,
};
