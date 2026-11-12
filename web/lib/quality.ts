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
  // Places the page prints a value of this metric to (the file keeps four); the table's `title`
  // carries the whole value.
  decimals: number;
  // A share runs on its own 0 to 100 scale; the others on the extent of their values.
  share?: boolean;
  // A value the chart draws as a line, and what it is.
  reference?: { value: number; text: string };
}

// The metrics the per-match table shows, one column each; a match missing a
// metric (e.g. football has no entry_angle) renders that cell empty.
export const TABLE_METRICS: TableMetric[] = [
  { check: "detection", metric: "ball_detected_pct", label: "Ball detected", unit: "%", decimals: 1, share: true },
  { check: "detection", metric: "player_detected_pct", label: "Player detected", unit: "%", decimals: 1, share: true },
  {
    check: "gravity",
    metric: "g_median",
    label: "Median g",
    unit: "m/s²",
    decimals: 2,
    reference: { value: HOOK.g_real, text: `standard gravity, ${HOOK.g_real} m/s²` },
  },
  {
    check: "gravity",
    metric: "g_median_bias_pct",
    label: "g bias",
    unit: "%",
    decimals: 1,
    reference: { value: 0, text: `0%, standard gravity (${HOOK.g_real} m/s²)` },
  },
  { check: "entry_angle", metric: "gap_median_deg", label: "Entry angle gap", unit: "°", decimals: 1 },
  { check: "noise", metric: "ball_player_d2_ratio", label: "Ball/player jitter", unit: "×", decimals: 1 },
  { check: "clock", metric: "clock_step_exact_pct", label: "Clock step exact", unit: "%", decimals: 1, share: true },
];

export const formatMetric = (m: TableMetric, value: number): string => value.toFixed(m.decimals);

export const QUALITY_SPORTS = ["basketball", "football"] as const;

// The middle value, or the mean of the two middle ones.
export function median(xs: readonly number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const k = s.length >> 1;
  return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2;
}

export interface SportSeries {
  sport: string;
  points: { match_id: string; value: number }[];
  median: number;
}

// One metric's values per sport, in match order; null for a sport the file has no row of, where
// the check does not apply.
export function seriesOf(m: TableMetric): Record<string, SportSeries | null> {
  const rows = (CHECKS[m.check] ?? []).filter((r) => r.metric === m.metric);
  return Object.fromEntries(
    QUALITY_SPORTS.map((sport) => {
      const points = rows
        .filter((r) => r.sport === sport)
        .map((r) => ({ match_id: r.match_id, value: r.value }))
        .sort((a, b) => a.match_id.localeCompare(b.match_id));
      return [sport, points.length ? { sport, points, median: median(points.map((p) => p.value)) } : null];
    }),
  );
}

// 1, 2 or 5 times a power of ten, the first at least `raw`.
function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((k) => k * p).find((s) => s >= raw)!;
}

export interface ChartScale {
  domain: [number, number];
  ticks: number[];
  // Places a tick's label needs.
  tickDecimals: number;
}

// The axis of a metric's chart: 0 to 100 for a share; otherwise the values and the reference,
// widened to whole steps of about a quarter of their span.
export function scaleOf(m: TableMetric, values: readonly number[]): ChartScale {
  if (m.share) return { domain: [0, 100], ticks: [0, 50, 100], tickDecimals: 0 };
  const all = m.reference ? [...values, m.reference.value] : [...values];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const step = niceStep(Math.max(hi - lo, 1e-6) / 4);
  const domain: [number, number] = [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
  if (domain[0] === domain[1]) domain[1] += step;
  const ticks: number[] = [];
  for (let t = domain[0]; t <= domain[1] + step / 2; t += step) ticks.push(Math.round(t / step) * step);
  return { domain, ticks, tickDecimals: Math.max(0, -Math.floor(Math.log10(step) + 1e-9)) };
}

// Where a value sits across the axis, in per cent of its width.
export const across = (domain: readonly [number, number], v: number): number => (100 * (v - domain[0])) / (domain[1] - domain[0]);

// The dots of a dot plot: matches whose values fall in the same sixtieth of the axis stack up.
export function stacked(points: readonly { match_id: string; value: number }[], domain: readonly [number, number], bins = 60) {
  const seen = new Map<number, number>();
  return points.map((p) => {
    const x = across(domain, p.value);
    const bin = Math.min(bins - 1, Math.floor((x / 100) * bins));
    const level = seen.get(bin) ?? 0;
    seen.set(bin, level + 1);
    return { ...p, x, level };
  });
}

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

// The checks the per-match table has a column for and the report has rows of: what the page
// counts when it says how many checks it shows.
export function tabulatedChecks(): string[] {
  const kept = new Set(Object.entries(CHECKS).flatMap(([check, rows]) => (rows.length ? [check] : [])));
  return [...new Set(TABLE_METRICS.map((m) => m.check))].filter((c) => kept.has(c));
}
