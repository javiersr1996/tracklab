// `web/public/data/platform.json` and `lineage.json` (tasks 34, 33), imported at
// build time like `lib/data.ts`: every figure on `/platform` is the one these two
// files were built with.
import platformJson from "../public/data/platform.json";
import lineageJson from "../public/data/lineage.json";

export type LayerName = "raw" | "bronze" | "silver" | "gold" | "quality" | "publish";

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
  // publish only: what the site watches and what /warehouse queries, split by use, which add up
  // to `bytes` (task 46, decision 10), and why "out" is not a live rescan (task 34, decision 1)
  watch_files?: number;
  watch_bytes?: number;
  query_files?: number;
  query_bytes?: number;
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

export interface PlatformStep {
  step_key: string;
  assets: string[];
  group: string;
  status: string;
  duration_ms: number;
  // Per-model dbt "Execution Duration" (task 32), keyed by asset key; only
  // the `silver` step has entries, one per dbt model or seed it ran.
  dbt_seconds: Record<string, number>;
}

export interface PlatformTable {
  layer: LayerName;
  sport: string | null;
  table: string;
  files: number;
  rows: number;
  bytes: number;
}

export interface PlatformMatch {
  sport: string;
  match_id: number;
  raw_bytes: number;
  raw_bytes_read: number;
  bronze_tracking_rows: number;
  silver_frames_rows: number;
  silver_events_rows: number;
  published_possessions: number;
  published_bytes: number;
}

export interface PlatformSeasonFileItem {
  sport: string;
  role: string;
  path: string;
  bytes: number;
}

export interface PlatformSeasonFiles {
  files: number;
  bytes: number;
  items: PlatformSeasonFileItem[];
}

// One ingest source's share of the raw layer (`disk.raw.sources[]` of the build record); the
// bytes add up to `layers[raw].bytes`.
export interface PlatformRawSource {
  source_id: string;
  sport: string;
  files: number;
  bytes: number;
}

export interface PlatformData {
  schema_version: number;
  title: string;
  subtitle: string;
  run: PlatformRun;
  layers: PlatformLayer[];
  raw_sources: PlatformRawSource[];
  steps: PlatformStep[];
  tables: PlatformTable[];
  matches: PlatformMatch[];
  season_files: PlatformSeasonFiles;
}

// Via unknown: the JSON's inferred `steps` type is a union of the steps' own `dbt_seconds` keys.
export const PLATFORM = platformJson as unknown as PlatformData;

export const POSE_SOURCE_ID = "opendata-bodypose";

// What the P6 body-pose zips add to "in": their files and bytes, and the bytes of every other
// raw source, all read from `raw_sources[]`, never typed. `null` if the source is not there.
export function poseShare(
  platform: PlatformData = PLATFORM,
): { files: number; bytes: number; otherBytes: number } | null {
  const pose = platform.raw_sources.find((s) => s.source_id === POSE_SOURCE_ID);
  if (!pose) return null;
  const otherBytes = platform.raw_sources
    .filter((s) => s.source_id !== POSE_SOURCE_ID)
    .reduce((sum, s) => sum + s.bytes, 0);
  return { files: pose.files, bytes: pose.bytes, otherBytes };
}

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

export interface SilverModelRow {
  key: string;
  dbt_columns: string[];
  dbt_tests: number;
  rows: number | null;
  bytes: number | null;
  dbt_seconds: number | null;
}

// The per-silver-model table (task 36): the 12 dbt-owned nodes of the
// `silver` lineage group (10 models, 2 seeds; task 33). `dbt_tests` and
// `dbt_columns` come from `lineage.json`; `dbt_seconds` from the `silver`
// step's own per-asset dbt timing. `rows`/`bytes` come from `platform.json`'s
// `tables[]`, matched by stripping the `silver_`/`seed_` prefix from the
// lineage key -- but only two of dbt's ten silver models (`frame_possession`,
// `frames_attacking`) are views with no Parquet file of their own, and
// neither seed writes one either, so those four rows get `null`, never an
// invented 0.
export function silverModelRows(
  lineage: LineageData = LINEAGE,
  platform: PlatformData = PLATFORM,
): SilverModelRow[] {
  const silverStep = platform.steps.find((s) => s.step_key === "silver");
  const dbtSeconds = silverStep?.dbt_seconds ?? {};
  const tableByName = new Map(
    platform.tables.filter((t) => t.layer === "silver").map((t) => [t.table, t]),
  );
  return lineage.nodes
    .filter((n) => n.group === "silver" && n.schema === "dbt")
    .map((n) => {
      const tableName = n.key.replace(/^(silver_|seed_)/, "");
      const table = tableByName.get(tableName);
      return {
        key: n.key,
        dbt_columns: n.dbt_columns ?? [],
        dbt_tests: n.dbt_tests ?? 0,
        rows: table?.rows ?? null,
        bytes: table?.bytes ?? null,
        dbt_seconds: dbtSeconds[n.key] ?? null,
      };
    })
    .sort((a, b) => a.key.localeCompare(b.key));
}

// The four fields the flow animates per layer; `rows` is skipped where the
// record has none (raw and publish count files, not table rows).
export type CounterField = "files" | "rows" | "bytes" | "seconds" | "downloaded" | "verified" | "bytes_read";

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
