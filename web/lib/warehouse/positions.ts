// What /warehouse/positions draws (task 184a), as plain functions the page, its figure and the
// tests share: the quartiles DuckDB's `quantile_cont` gives, the query that reproduces them in the
// console, the axis of a metric and where each position group stands on the pitch.

import { footballPrimitives } from "../geometry/football";

// The pitch's markings as one SVG path in metres, the origin at the centre and y down.
export function pitchPath(length: number, width: number): string {
  const n = (v: number) => Math.round(v * 100) / 100;
  return footballPrimitives(length, width)
    .map((p) => {
      if (p.kind === "line") return `M${n(p.x1)} ${n(p.y1)}L${n(p.x2)} ${n(p.y2)}`;
      if (p.kind === "rect") return `M${n(p.x)} ${n(p.y)}h${n(p.w)}v${n(p.h)}h${n(-p.w)}Z`;
      if (p.kind === "circle") return `M${n(p.cx - p.r)} ${n(p.cy)}a${n(p.r)} ${n(p.r)} 0 1 0 ${n(2 * p.r)} 0a${n(p.r)} ${n(p.r)} 0 1 0 ${n(-2 * p.r)} 0`;
      const at = (a: number) => `${n(p.cx + p.r * Math.cos(a))} ${n(p.cy + p.r * Math.sin(a))}`;
      return `M${at(p.start)}A${n(p.r)} ${n(p.r)} 0 ${p.end - p.start > Math.PI ? 1 : 0} 1 ${at(p.end)}`;
    })
    .join("");
}

// The physical metrics of `fb_physical` the page compares, by their id in scouting.json.
export const POSITION_METRIC_IDS = ["total_metersperminute_full_all", "hsr_distance_full_all", "sprint_distance_full_all", "psv99"] as const;

// Where each group plays on a pitch drawn with its own goal on the left: x along the pitch and y
// across it (down), both from -1 to 1. A group the data has and this list does not fails the build.
export const SPOTS: Record<string, { x: number; y: number }> = {
  "Central Defender": { x: -0.64, y: 0 },
  "Full Back": { x: -0.3, y: 0.7 },
  Midfield: { x: 0.04, y: 0 },
  "Wide Attacker": { x: 0.36, y: -0.7 },
  "Center Forward": { x: 0.68, y: 0 },
};

// DuckDB's quantile_cont: linear between the two closest ranks of the sorted values.
export function quantileCont(sorted: readonly number[], q: number): number {
  const at = (sorted.length - 1) * q;
  const lo = Math.floor(at);
  const hi = Math.ceil(at);
  return sorted[lo] + (at - lo) * (sorted[hi] - sorted[lo]);
}

// DuckDB's round(x, d) on a double: x times 10^d, to the nearest whole number, back. Formatting the
// double itself can land on the other side of a tie (29.565 is printed 29.56 and rounded 29.57), so
// the page rounds first and prints what the query returns.
export const roundAsDuckDb = (v: number, d: number): number => Math.round(v * 10 ** d) / 10 ** d;

export interface GroupView {
  group: string;
  n: number;
  q1: number;
  median: number;
  q3: number;
  // The three as the page prints them.
  text: { q1: string; median: string; q3: string };
  // Every player of the pool, ascending.
  values: number[];
}

export interface MetricView {
  id: string;
  label: string;
  unit: string;
  // "per match, m", as the scouting table's column head says it.
  scale: string;
  domain: [number, number];
  ticks: { value: number; text: string }[];
  groups: GroupView[];
  // The console query that returns the same n and quartiles.
  sql: string;
}

export interface PositionsView {
  metrics: MetricView[];
  floor: string;
  floorMin: number;
  competition: string;
  season: string;
  // The pitch's size in metres, from a published football possession.
  pitch: { length: number; width: number };
}

export function groupView(group: string, values: readonly number[], format: (v: number) => string): GroupView {
  const sorted = [...values].sort((a, b) => a - b);
  const [q1, median, q3] = [0.25, 0.5, 0.75].map((q) => quantileCont(sorted, q));
  return { group, n: sorted.length, q1, median, q3, text: { q1: format(q1), median: format(median), q3: format(q3) }, values: sorted };
}

// The axis of one metric across every group: whole steps of 1, 2 or 5 times a power of ten, about
// four of them.
export function axisOf(values: readonly number[]): { domain: [number, number]; ticks: number[]; decimals: number } {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const raw = Math.max(hi - lo, 1e-6) / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((k) => k * p).find((s) => s >= raw)!;
  const domain: [number, number] = [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
  const ticks: number[] = [];
  for (let t = domain[0]; t <= domain[1] + step / 2; t += step) ticks.push(Math.round(t / step) * step);
  return { domain, ticks, decimals: Math.max(0, -Math.floor(Math.log10(step) + 1e-9)) };
}

export const across = (domain: readonly [number, number], v: number): number => (100 * (v - domain[0])) / (domain[1] - domain[0]);

// The query a reader can paste into /warehouse's console: the pool of the scouting page (the rows
// that pass its floor, a metric's NULLs left out), counted and cut into quartiles by group.
export function positionsSql(column: string, floor: string, decimals: number): string {
  if (!/^[a-z][a-z0-9_]*$/.test(column)) throw new Error(`${column} is not a plain column name`);
  const q = (p: number, name: string) => `round(quantile_cont(${column}, ${p}), ${decimals}) AS ${name}`;
  return `SELECT position_group,
       count(*) AS n,
       ${q(0.25, "q1")},
       ${q(0.5, "median")},
       ${q(0.75, "q3")}
FROM fb_physical
WHERE ${floor} AND ${column} IS NOT NULL
GROUP BY position_group
ORDER BY median DESC, position_group`;
}
