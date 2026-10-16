// A published pose clip (task 55 of tasks/todo.md, P6), as validated by schema.json.

import type { Surface } from "../replay/types";

// 29 [dx, dy, dz] in whole cm from the player's own (x, y, 0), in the order of `joints`
// (z is relative to the player's centroid, not a height above the pitch), then the 29
// p90_mae_cm in whole mm.
export type Joints = [xyz: [number, number, number][], mae: number[]];

// [index into `players`, x_cm, y_cm, is_detected 0/1 (null in the clips of a whole match, which
// the one reader of the bronze gives no flag), joints or null]. A null joints is a player the
// file has no pose for in that frame: it is never interpolated or carried over.
export type PlayerAt = [i: number, x: number, y: number, detected: 0 | 1 | null, joints: Joints | null];

export interface PoseFrame {
  f: number;
  t: number;
  ball: [x: number, y: number, detected: 0 | 1];
  p: PlayerAt[];
}

export interface Limit {
  id: string;
  readme: string;
  text: string;
}

export interface PosePlayer {
  player_id: number;
  team_id: number;
  number: number;
}

export interface PoseCoverage {
  frames: number;
  player_frames: number;
  with_joints: number;
  with_joints_share: number;
  joint_observations: number;
  skeletons_per_frame: { min: number; max: number };
  p90_mae_cm: { min: number; median: number; p90: number; max: number };
}

// A window of the hook player inside a clip of a whole match (task 62): `s_mm` is s(t) in whole
// millimetres, one value per frame from frame_lo to frame_hi; the cadence and its sd are the
// metric's, null when NaN.
export interface PoseWindow {
  player: number;
  band: "low" | "high";
  frame_lo: number;
  frame_hi: number;
  speed_m_s: number;
  cadence_hz: number | null;
  cadence_sd_hz: number | null;
  s_mm: number[];
}

export interface PoseClip {
  schema_version: 1;
  match_id: number;
  period: number;
  frame_lo: number;
  frame_hi: number;
  fps: 25;
  tracking_frame_factor: 2.5;
  surface: Surface;
  source: { file: string; bytes: number; sha256: string };
  units: { xy: string; joints: string; mae: string };
  joints: string[];
  bones: [number, number][];
  limits: Limit[];
  teams: { team_id: number; side: "home" | "away" }[];
  players: PosePlayer[];
  coverage: PoseCoverage;
  // Only in the clips of a whole match.
  selection?: { kind: "hook" | "stretch"; rule: string } & Record<string, unknown>;
  windows?: PoseWindow[];
  frames: PoseFrame[];
}

// `pose.json` (task 62), as validated by summary.schema.json: what /pose says. Its figures are
// read from pipeline/reports/, never typed.
export type PoseStatus = "alive" | "unreplicated" | "dead";

export interface PoseClipRecord {
  match_id: number;
  kind: "hook" | "stretch";
  file: string;
  bytes: number;
  sha256: string;
  period: number;
  frame_lo: number;
  frame_hi: number;
  coverage: PoseCoverage;
  selection: { kind: "hook" | "stretch"; rule: string } & Record<string, unknown>;
  windows: { player: number; band: string; frame_lo: number; frame_hi: number }[];
}

export interface CoverageCounts {
  frames: number;
  frames_with_pose: number;
  player_frames: number;
  with_pose: number;
  share_frames_with_pose: number;
  share_player_frames_with_pose: number;
  skeletons_per_frame: { mean_over_frames_with_pose: number | null; min_over_frames_with_pose: number | null; max: number };
}

export interface PoseMatchTables {
  note: string;
  columns: string[];
  // match id -> rows, by team and shirt number; each row follows `columns`.
  matches: Record<string, (string | number | null)[][]>;
  m3: string;
  order: string;
}

export interface PoseSummary {
  schema_version: 1;
  status: PoseStatus;
  dead_at: "noise" | "M1" | "M2" | "M4" | null;
  limits: Limit[];
  protocol: {
    stage: string;
    calibration: number;
    confirmation: number;
    width: number | null;
    cap_cm: number | null;
    bands: { low_m_s: number[]; high_m_s_from: number };
    numbers: Record<string, unknown>;
    blind_spots: string[];
    stages: { stage: string; sha256: string; what: string; code_tree_sha?: string }[];
  };
  // Its shape depends on how far the verdict got; the page reads it by path.
  verdict: Record<string, unknown> & { source: string };
  opened: {
    confirmation_match_opened: boolean;
    at_the_freeze: { not_seen: string; consequence: string };
    not_opened: number[];
  };
  coverage: Record<string, { periods: Record<string, CoverageCounts>; total: CoverageCounts; players_with_pose: number; mae_cm: Record<string, unknown> }>;
  phase406: { file: string; bytes: number; sha256: string; coverage: PoseCoverage };
  clips: PoseClipRecord[];
  tables: PoseMatchTables | null;
}
