// A published pose clip (task 55 of tasks/todo.md, P6), as validated by schema.json.

import type { Surface } from "../replay/types";

// 29 [dx, dy, dz] in whole cm from the player's own (x, y, 0), in the order of `joints`
// (z is relative to the player's centroid, not a height above the pitch), then the 29
// p90_mae_cm in whole mm.
export type Joints = [xyz: [number, number, number][], mae: number[]];

// [index into `players`, x_cm, y_cm, is_detected 0/1, joints or null]. A null is a player the
// file has no pose for in that frame: it is never interpolated or carried over.
export type PlayerAt = [i: number, x: number, y: number, detected: 0 | 1, joints: Joints | null];

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
  frames: PoseFrame[];
}
