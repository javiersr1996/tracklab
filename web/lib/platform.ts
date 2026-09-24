// `web/public/data/platform.json` and `lineage.json` (tasks 34, 33), imported at
// build time like `lib/data.ts`: every figure on `/platform` is the one these two
// files were built with.
import platformJson from "../public/data/platform.json";
import lineageJson from "../public/data/lineage.json";

export type LayerName = "raw" | "bronze" | "silver" | "quality" | "publish";

export interface PlatformLayer {
  layer: LayerName;
  files: number;
  rows: number | null;
  bytes: number;
  seconds: number;
  seconds_sum: number;
  // raw only
  bytes_pinned?: number;
  bytes_read?: number;
  downloaded?: number;
  verified?: number;
  // publish only: why "out" is not a live rescan of web/public/data (task 34, decision 1)
  note?: string;
}

export interface PlatformRun {
  git_sha: string;
  started_utc: string;
  finished_utc: string;
  wall_seconds: number;
  host: { system: string; cpus: number; ram_gb: number };
  versions: Record<string, string>;
}

export interface PlatformData {
  schema_version: number;
  title: string;
  run: PlatformRun;
  layers: PlatformLayer[];
}

export const PLATFORM = platformJson as PlatformData;
export const LAYERS = PLATFORM.layers;

export interface LineageNode {
  key: string;
  group: string;
  kind: "asset" | "external";
  description: string;
  step: string | null;
  sport: string | null;
  schema: "frozen" | "code" | "dbt" | "none";
  dbt_tests?: number;
  dbt_columns?: string[];
}

export interface LineageEdge {
  from: string;
  to: string;
}

export interface LineageData {
  schema_version: number;
  groups: string[];
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export const LINEAGE = lineageJson as LineageData;

// The four fields the flow animates per layer; `rows` is skipped where the
// record has none (raw and publish count files, not table rows).
export type CounterField = "files" | "rows" | "bytes" | "seconds";

export const COUNTER_FIELDS: CounterField[] = ["files", "rows", "bytes", "seconds"];

export function counterKey(layer: LayerName, field: CounterField): string {
  return `${layer}.${field}`;
}

// Per-layer on-screen seconds for the flow animation (task 35): every layer
// gets at least `minSeconds` of screen time, and the rest of the loop budget
// is split among layers in proportion to their own slowest step
// (`layers[].seconds`), so a layer that took longer to build gets more
// screen time and a layer that took 0s in the record still plays for
// `minSeconds` instead of flashing by or breaking the scale.
export function layerDurations(seconds: number[], cycleSeconds = 8, minSeconds = 0.6): number[] {
  const floor = minSeconds * seconds.length;
  const extra = Math.max(cycleSeconds - floor, 0);
  const totalWeight = seconds.reduce((sum, s) => sum + Math.max(s, 0), 0);
  return seconds.map((s) => {
    const share = totalWeight > 0 ? Math.max(s, 0) / totalWeight : 1 / seconds.length;
    return minSeconds + share * extra;
  });
}
