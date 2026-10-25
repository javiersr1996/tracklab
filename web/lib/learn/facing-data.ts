// Lesson 11's data, computed at build time from the two clips /pose publishes (P6, task 62) and
// nothing else: nothing new is published. For every player of each clip, the frames where the
// player has both shoulders and the nose, a position in the frame before and the frame after,
// and a speed over the lesson's floor, with the three angles of `facing.ts`. The page passes the
// angles to its figures (and, for the clip's hook player, the three joints that draw one frame)
// and leaves the clips on the server.
import hook1925299 from "../../public/data/pose/hook_1925299.json";
import hook1996435 from "../../public/data/pose/hook_1996435.json";
import pose from "../../public/data/pose.json";
import type { PlayerAt, PoseClip, PoseSummary } from "../pose/types";
import { centralSpeed, facingDeg, type FacingSummary, type FrameFacing, headingDeg, MIN_FRAMES, MIN_SPEED_M_S, relativeDeg, summarise, type XY } from "./facing";

// Each clip as `pose.json` lists it, by its path under `public/data/`.
export const CLIPS: Readonly<Record<string, PoseClip>> = {
  "pose/hook_1925299.json": hook1925299 as unknown as PoseClip,
  "pose/hook_1996435.json": hook1996435 as unknown as PoseClip,
};

export interface FrameView extends FrameFacing {
  // The joints that give the facing, as [dx, dy] in cm from the player's own x, y.
  left: XY;
  right: XY;
  nose: XY;
}

export interface HookPlayer {
  index: number;
  player_id: number;
  team_id: number;
  number: number;
  frames: FrameView[];
}

export interface PlayerFacing extends FacingSummary {
  index: number;
  player_id: number;
  team_id: number;
  number: number;
}

export interface ClipFacing {
  file: string;
  match_id: number;
  fps: number;
  clip_frames: number;
  hook: HookPlayer;
  players: PlayerFacing[]; // the players with at least MIN_FRAMES qualifying frames, in the file's order
}

const xy = (p: PlayerAt): XY => [p[1], p[2]];

// A player's qualifying frames, in frame order. A frame qualifies when the player is in the clip
// at f − 1, f and f + 1, has the nose and both shoulders at f with the nose off the shoulder line,
// and moves faster than MIN_SPEED_M_S over the two neighbours (cm to m, twice the frame step).
export function playerFrames(clip: PoseClip, index: number): FrameView[] {
  const nose = clip.joints.indexOf("nose");
  const left = clip.joints.indexOf("lShoulder");
  const right = clip.joints.indexOf("rShoulder");
  if (nose < 0 || left < 0 || right < 0) throw new Error("the clip has no nose or shoulders");
  const dt = 1 / clip.fps;
  const rows = new Map<number, PlayerAt>();
  for (const fr of clip.frames) for (const p of fr.p) if (p[0] === index) rows.set(fr.f, p);
  const out: FrameView[] = [];
  for (const [f, p] of [...rows.entries()].sort((a, b) => a[0] - b[0])) {
    const before = rows.get(f - 1);
    const after = rows.get(f + 1);
    if (!before || !after || !p[4]) continue;
    const [joints] = p[4];
    const l = joints[left];
    const r = joints[right];
    const n = joints[nose];
    if (!l || !r || !n) continue;
    const L: XY = [l[0], l[1]];
    const R: XY = [r[0], r[1]];
    const N: XY = [n[0], n[1]];
    const facing = facingDeg(L, R, N);
    if (Number.isNaN(facing)) continue;
    const speed = centralSpeed(xy(before), xy(after), dt) / 100;
    if (speed <= MIN_SPEED_M_S) continue;
    const heading = headingDeg(xy(before), xy(after));
    out.push({ f, speed, facing, heading, relative: relativeDeg(facing, heading), left: L, right: R, nose: N });
  }
  return out;
}

export function clipFacing(file: string, clip: PoseClip): ClipFacing {
  const hook = clip.windows?.[0]?.player;
  if (hook === undefined) throw new Error(`${file} names no hook player`);
  const players: PlayerFacing[] = [];
  let hookFrames: FrameView[] | null = null;
  clip.players.forEach((who, index) => {
    const frames = playerFrames(clip, index);
    if (index === hook) hookFrames = frames;
    if (frames.length >= MIN_FRAMES) players.push({ index, ...who, ...summarise(frames) });
  });
  if (!hookFrames || (hookFrames as FrameView[]).length < MIN_FRAMES) throw new Error(`${file}: the hook player has too few qualifying frames`);
  const who = clip.players[hook];
  return {
    file,
    match_id: clip.match_id,
    fps: clip.fps,
    clip_frames: clip.frames.length,
    hook: { index: hook, ...who, frames: hookFrames },
    players,
  };
}

export const FACING: readonly ClipFacing[] = Object.entries(CLIPS).map(([file, clip]) => clipFacing(file, clip));

export const POSE = pose as unknown as PoseSummary;

// A value of a published file by its `data-fig` name, "<file under public/data>:<dotted path>":
// `pose.json` or one of the clips.
export function publishedFigure(name: string): unknown {
  const [file, path] = name.split(":");
  const root: unknown = file === "pose.json" ? POSE : CLIPS[file];
  return path.split(".").reduce<unknown>((at, key) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[key] : undefined), root);
}
