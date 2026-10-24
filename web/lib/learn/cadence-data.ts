// Lesson 5's slice of what /pose publishes (P6, task 62), read at build time: the hook window of
// each published clip and the fast-band row of every player in `pose.json`'s tables. Nothing new
// is published; the page passes these few hundred numbers to its figures and leaves the clips on
// the server. Every figure is the file's, or computed from it in `cadence.ts`.
import hook1925299 from "../../public/data/pose/hook_1925299.json";
import hook1996435 from "../../public/data/pose/hook_1996435.json";
import pose from "../../public/data/pose.json";
import type { PoseClip, PoseSummary } from "../pose/types";

export const POSE = pose as unknown as PoseSummary;

// Each clip as `pose.json` lists it, by its path under `public/data/`.
export const CLIPS: Readonly<Record<string, PoseClip>> = {
  "pose/hook_1925299.json": hook1925299 as unknown as PoseClip,
  "pose/hook_1996435.json": hook1996435 as unknown as PoseClip,
};

export interface HookWindow {
  file: string;
  match_id: number;
  team_id: number;
  number: number;
  fps: number;
  speed_m_s: number;
  cadence_hz: number; // as published, from the unrounded joints
  cadence_sd_hz: number;
  s_m: number[]; // the published s(t), whole millimetres, in metres
  joints_s_m: number[]; // s(t) again, from the clip's joints in whole centimetres
  sigma_m: number[]; // per frame, the sd of s from the two ankles' predicted errors
}

export function hookWindow(file: string, clip: PoseClip): HookWindow {
  const w = clip.windows?.[0];
  if (!w || w.cadence_hz === null || w.cadence_sd_hz === null) throw new Error(`${file} has no hook window with a cadence`);
  const left = clip.joints.indexOf("lAnkle");
  const right = clip.joints.indexOf("rAnkle");
  const rows = clip.frames
    .filter((f) => f.f >= w.frame_lo && f.f <= w.frame_hi)
    .map((f) => f.p.find((p) => p[0] === w.player));
  if (rows.length !== w.s_mm.length || rows.some((p) => !p || !p[4])) throw new Error(`${file}: the window's frames are not all in the clip`);
  const at = rows.map((p) => ({ x: p![1], y: p![2], xyz: p![4]![0], mae: p![4]![1] }));
  // The direction of travel: the net displacement of the player's x, y over the window (gait.py).
  const dx = at[at.length - 1].x - at[0].x;
  const dy = at[at.length - 1].y - at[0].y;
  const norm = Math.hypot(dx, dy);
  const player = clip.players[w.player];
  return {
    file,
    match_id: clip.match_id,
    team_id: player.team_id,
    number: player.number,
    fps: clip.fps,
    speed_m_s: w.speed_m_s,
    cadence_hz: w.cadence_hz,
    cadence_sd_hz: w.cadence_sd_hz,
    s_m: w.s_mm.map((v) => v / 1000),
    // Joints in cm, predicted errors in mm (lib/pose/types.ts).
    joints_s_m: at.map((a) => ((a.xyz[left][0] - a.xyz[right][0]) * dx + (a.xyz[left][1] - a.xyz[right][1]) * dy) / norm / 100),
    sigma_m: at.map((a) => Math.hypot(a.mae[left], a.mae[right]) / 1000),
  };
}

export const HOOKS: readonly HookWindow[] = Object.entries(CLIPS).map(([file, clip]) => hookWindow(file, clip));

export interface PlayerRow {
  match: string;
  row: number; // index in `tables.matches[match]`, for the figure's path
  team_id: number;
  number: number;
  finite_s: number;
  cadence_hz: number;
  sd_hz: number;
}

// Every player's row for the fast band over the whole match, with at least the protocol's floor
// of windows with a cadence; in the file's order, by team and shirt number, never by a metric.
export function fastRows(doc: PoseSummary): Record<string, PlayerRow[]> {
  const tables = doc.tables;
  if (!tables) return {};
  const col = (name: string) => {
    const i = tables.columns.indexOf(name);
    if (i < 0) throw new Error(`pose.json has no column ${name}`);
    return i;
  };
  const floor = Number(doc.protocol.numbers.min_windows);
  const [team, number, period, band, finite, cad, sdCol] = ["team_id", "number", "period", "band", "finite_s", "cad_s_p50_hz", "cad_s_sd_hz"].map(col);
  return Object.fromEntries(
    Object.entries(tables.matches).map(([match, rows]) => [
      match,
      rows.flatMap((r, row) =>
        r[period] === "all" && r[band] === "high" && Number(r[finite]) >= floor && r[cad] !== null && r[sdCol] !== null
          ? [{ match, row, team_id: Number(r[team]), number: Number(r[number]), finite_s: Number(r[finite]), cadence_hz: Number(r[cad]), sd_hz: Number(r[sdCol]) }]
          : [],
      ),
    ]),
  );
}

export const FAST_ROWS = fastRows(POSE);

// The column index of a name in the tables, for a `data-fig` path into a row.
export const column = (name: string): number => POSE.tables?.columns.indexOf(name) ?? -1;

// A value of a published file by its `data-fig` name, "<file under public/data>:<dotted path>".
export function publishedFigure(name: string): unknown {
  const [file, path] = name.split(":");
  const root: unknown = file === "pose.json" ? POSE : CLIPS[file];
  return path.split(".").reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), root);
}
