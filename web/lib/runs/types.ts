// `web/public/data/runs.json` (task 52), as `lib/runs/schema.json` describes it. Only what
// `/runs` reads is typed; the report subtrees stay loose and are reached through `at`.

export type Stage = "M1" | "M2" | "M3" | "M4" | "M5a" | "M5b";
export const STAGES: Stage[] = ["M1", "M2", "M3", "M4", "M5a", "M5b"];

export interface StageEntry {
  state: string;
  rule: string;
  figures: Record<string, unknown>;
}

export interface PerMatchRow {
  match_id: number;
  [key: string]: number | string;
}

export interface Pooled {
  pairs: number;
  mean_m: number;
  same_sign_matches: number;
  of_matches: number;
  p: number;
  passes_bar: boolean;
}

export interface SubtypeEffect {
  subtype: string;
  marker: { per_match: PerMatchRow[]; pooled: Pooled };
  line: { testability: string; per_match: PerMatchRow[]; pooled: Pooled };
  pre_trend: { per_match: PerMatchRow[]; pooled: { ratio: number } };
  fully_detected: { per_match: PerMatchRow[]; pooled: { ratio: number } };
  verdict: {
    passes_bar: boolean;
    M3: { pre_trend_ratio: number; leaves: boolean };
    M4: { detected_ratio: number; leaves: boolean };
    candidate: boolean;
  };
}

export interface KinematicsPooled {
  [key: string]: number;
}

export interface Defence {
  entity_id: string;
  is_goalkeeper: boolean;
  is_marker: boolean;
  displacement_m: number;
}

export interface Clip {
  role: "run" | "placebo";
  file: string;
  instant_index: number;
  frames: number;
  window_s: [number, number];
  marker_entity_id: string;
  marker_displacement_m: number;
  defence: Defence[];
}

export interface Runs {
  schema_version: number;
  sources: { protocol: string; calibration: string; coverage: string };
  status: "alive" | "dead";
  dead_at: Stage | null;
  stages: Record<Stage, StageEntry>;
  funnel: {
    probe: { per_match: { match_id: number; half: string; runs: number; pairs: number }[] };
    coverage: PerMatchRow[];
  };
  effect_by_subtype: SubtypeEffect[];
  instrument: {
    marker: { per_match: PerMatchRow[]; pooled: Pooled };
  };
  design_checks: { cadence: { windows: { effect_s: number } } };
  power: { rows: PerMatchRow[]; target_pass_rate: number };
  null: {
    per_match: PerMatchRow[];
    per_subtype: { subtype: string; pairs: number; fires_pct: number }[];
    at_least_one_pct: number;
  };
  post_hoc_kinematics: {
    label: string;
    thresholds: Record<string, number>;
    per_subtype: { subtype: string; per_match: PerMatchRow[]; pooled: KinematicsPooled }[];
  };
  protocol: {
    stage: string;
    stages_seen: string[];
    frozen: boolean;
    fingerprint: string;
    content_sha256: string;
    calibration_sha256: string;
    history: { stage: string; task: number; date: string; note?: string }[];
    question: string;
    windows: { velocity_s: number };
    quantities: { secondary_rule: string };
    bar: {
      calibration: { same_sign_matches_at_least: number; of_matches: number; p_at_most: number };
      held_out: { same_sign_matches_at_least: number; of_matches: number; p_at_most: number };
    };
  };
  never_opened: {
    half: string;
    opened: boolean;
    match_ids: number[];
    counts: PerMatchRow[];
  };
  hook: {
    rule: string;
    subtype: string;
    subtype_pairs: number;
    eligible_pairs: number;
    subtype_median_marker_m: number;
    pair: {
      match_id: number;
      run_id: string;
      runner_entity_id: string;
      marker_effect_m: number;
      direction: [number, number];
    };
    clips: Clip[];
  };
}

// The value at a dotted path ("effect_by_subtype.0.marker.pooled.p"): how the page
// reads every figure it prints, and how the e2e finds the same one in the file.
export function at(root: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>((node, key) => (node as Record<string, unknown> | undefined)?.[key], root);
}
