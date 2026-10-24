// Lesson 8's data, read at build time: `public/data/learn/entry.json` (`tracklab learn entry`), the
// example's flight with the check's constants, and the entry-angle rows of `quality.json` (P3),
// the table. Only the server imports this file; the figure gets the example as a prop.
import entryJson from "../../public/data/learn/entry.json";
import { CHECKS, type QualityRow } from "../quality";
import type { EntryConstants, Sample } from "./entry";

export interface EntryExample {
  match_id: string;
  shot_id: string;
  start_frame: number;
  x: number[];
  y: number[];
  z: number[];
  rim_x: number;
  published: { v_h: number; d: number; t: number; k: number; reported: number; required: number };
  full_precision: { reported: number; required: number };
}

export interface EntryFile extends EntryConstants {
  schema_version: number;
  search_offset: number;
  digits: number;
  example: EntryExample;
}

export const ENTRY = entryJson as EntryFile;

// The example's samples from its start frame, at the time silver keeps (frame times 40 ms), and
// the run the check fits: from `search_offset` frames after the start.
export function samples(file: EntryFile): Sample[] {
  const ex = file.example;
  return ex.x.map((x, i) => {
    const f = ex.start_frame + i;
    return { t: Math.floor((f * 1000) / file.fps) / 1000, x, y: ex.y[i], z: ex.z[i] };
  });
}

export const ENTRY_SAMPLES = samples(ENTRY);
export const ENTRY_RUN = ENTRY_SAMPLES.slice(ENTRY.search_offset);

// One basketball match of `checks.entry_angle`.
export interface EntryMatch {
  match_id: string;
  calibration: boolean;
  shots: number;
  reported: number;
  required: number;
  gap: number;
  reordered: number;
}

export const ENTRY_METRICS = {
  shots: "shots",
  reported: "angle_reported_median_deg",
  required: "angle_required_median_deg",
  gap: "gap_median_deg",
  reordered: "pairs_reordered_pct",
} as const;

// The split into calibration and control matches is the gravity check's (`is_calibration`).
export function entryMatches(rows: readonly QualityRow[], gravity: readonly QualityRow[]): EntryMatch[] {
  const ids = [...new Set(rows.filter((r) => r.sport === "basketball").map((r) => r.match_id))].sort();
  return ids.map((match_id) => {
    const of = (metric: string) => {
      const row = rows.find((r) => r.match_id === match_id && r.metric === metric);
      if (!row) throw new Error(`quality.json has no ${metric} for ${match_id}`);
      return row.value;
    };
    return {
      match_id,
      calibration: gravity.some((r) => r.match_id === match_id && r.metric === "is_calibration" && r.value === 1),
      shots: of(ENTRY_METRICS.shots),
      reported: of(ENTRY_METRICS.reported),
      required: of(ENTRY_METRICS.required),
      gap: of(ENTRY_METRICS.gap),
      reordered: of(ENTRY_METRICS.reordered),
    };
  });
}

export const ENTRY_MATCHES = entryMatches(CHECKS.entry_angle, CHECKS.gravity);

// The `data-fig` name of a value of `checks.entry_angle`, as lesson 1 names quality.json's rows.
export const entryFig = (match_id: string, metric: string): string => `checks.entry_angle.${match_id}.${metric}`;
