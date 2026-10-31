import { drawSurface } from "../geometry";
import { COLORS, drawBall, drawDisc, layout } from "../replay/render";
import { byDepth, type Camera, project, type Projected } from "./project";
import type { Joints, PlayerAt, PoseClip, PoseFrame } from "./types";

// The pose viewer's drawing (task 56). The pitch is the replay's: flat, seen from above, with
// the same markings and scale. Each body is drawn in its own frame, projected by the camera
// about its own (x, y) on that pitch; z never lands on the pitch plane (limit 2 of P6). A
// player with no pose in the frame is the replay's disc (limit 1). Positions are the pose
// file's own x and y, never the tracking's.

export const SIDE_COLORS = { home: COLORS.attack, away: COLORS.defence };
// The followed player's ring: white (--canvas-hi, 20.1:1 on the canvas), not the discs' dark text.
export const RING_COLOR = "#ffffff";

// A joint's p90_mae in three bands cut at the clip's own median and 90th percentile (cm), read
// from `coverage.p90_mae_cm`; the further the band, the fainter the joint and its bones.
export const BAND_ALPHA = [1, 0.55, 0.2] as const;

export function maeBand(maeMm: number, cuts: { median: number; p90: number }): 0 | 1 | 2 {
  const cm = maeMm / 10;
  return cm <= cuts.median ? 0 : cm <= cuts.p90 ? 1 : 2;
}

// The joint the viewer reports through `window.__pose`, so a test can follow one point.
export const PROBE_JOINT = "nose";

export interface Probe {
  i: number;
  joint: string;
  u: number;
  v: number;
  depth: number;
}

export interface Drawn {
  skeletons: number;
  discs: number;
  probe: Probe | null;
}

const JOINT_PX = 1.5;
const BONE_PX = 1.5;
const RING_PX = 14;
const FOLLOW_SPAN_M = 2.6;
const FOLLOW_JOINT_PX = 4;
const FOLLOW_BONE_PX = 3;
const GRID_STEP_M = 0.25;
const GRID_HALF_M = 1;

function colorOf(clip: PoseClip, i: number): string {
  const team = clip.players[i].team_id;
  return clip.teams.find((t) => t.team_id === team)?.side === "away"
    ? SIDE_COLORS.away
    : SIDE_COLORS.home;
}

// The joints in metres of the body frame, projected: the origin is the player's (x, y, 0).
export function projectJoints(joints: Joints, camera: Camera): Projected[] {
  return joints[0].map(([dx, dy, dz]) => project(dx / 100, dy / 100, dz / 100, camera));
}

function strokeSkeleton(
  ctx: CanvasRenderingContext2D,
  clip: PoseClip,
  joints: Joints,
  points: Projected[],
  toPixel: (p: Projected) => [number, number],
  color: string,
  bonePx: number,
  jointPx: number,
): void {
  const cuts = clip.coverage.p90_mae_cm;
  const alpha = joints[1].map((mae) => BAND_ALPHA[maeBand(mae, cuts)]);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = bonePx;
  ctx.lineCap = "round";
  for (const [a, b] of byDepth(points, clip.bones)) {
    const [ax, ay] = toPixel(points[a]);
    const [bx, by] = toPixel(points[b]);
    ctx.globalAlpha = Math.min(alpha[a], alpha[b]);
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
  }
  points.forEach((p, j) => {
    const [px, py] = toPixel(p);
    ctx.globalAlpha = alpha[j];
    ctx.beginPath();
    ctx.arc(px, py, jointPx, 0, 2 * Math.PI);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

// The pitch, every player of the frame (a skeleton if the file gives him a pose, else a disc)
// and the ball. Returns what it drew: the counts `window.__pose` reports come from here.
export function drawPitch(
  ctx: CanvasRenderingContext2D,
  clip: PoseClip,
  frame: PoseFrame,
  camera: Camera,
  followed: number | null,
): Drawn {
  const { width, height } = ctx.canvas;
  const { scale, cx, cy } = layout(ctx.canvas, clip);
  const pixel = (x: number, y: number): [number, number] => [cx + x * scale, cy - y * scale];

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.setTransform(scale, 0, 0, -scale, cx, cy);
  ctx.strokeStyle = COLORS.surface;
  ctx.lineWidth = 1.5 / scale;
  drawSurface(ctx, clip.surface);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "bold 10px system-ui, sans-serif";

  let discs = 0;
  const bodies: { entry: PlayerAt; joints: Joints; anchor: number }[] = [];
  for (const entry of frame.p) {
    const [i, x, y, detected, joints] = entry;
    if (joints === null) {
      const [px, py] = pixel(x / 100, y / 100);
      drawDisc(ctx, px, py, colorOf(clip, i), String(clip.players[i].number), detected === 1);
      discs += 1;
    } else {
      bodies.push({ entry, joints, anchor: project(x / 100, y / 100, 0, camera)[2] });
    }
  }

  // The probe follows the followed player, else the first body in the frame's order.
  const target = bodies.find((b) => b.entry[0] === followed) ?? bodies[0];
  const probeIndex = clip.joints.indexOf(PROBE_JOINT);
  // Farther bodies first, so a nearer one is drawn over them.
  bodies.sort((a, b) => b.anchor - a.anchor);
  let probe: Probe | null = null;
  for (const body of bodies) {
    const [i, x, y] = body.entry;
    const points = projectJoints(body.joints, camera);
    const toPixel = ([u, v]: Projected) => pixel(x / 100 + u, y / 100 + v);
    strokeSkeleton(ctx, clip, body.joints, points, toPixel, colorOf(clip, i), BONE_PX, JOINT_PX);
    if (body === target) {
      const [u, v, depth] = points[probeIndex];
      probe = { i, joint: PROBE_JOINT, u, v, depth };
    }
  }

  const ring = frame.p.find((e) => e[0] === followed);
  if (ring) {
    const [px, py] = pixel(ring[1] / 100, ring[2] / 100);
    ctx.strokeStyle = RING_COLOR;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(px, py, RING_PX, 0, 2 * Math.PI);
    ctx.stroke();
  }

  const [bx, by] = pixel(frame.ball[0] / 100, frame.ball[1] / 100);
  ctx.globalAlpha = frame.ball[2] === 1 ? 1 : 0.45;
  drawBall(ctx, bx, by, null);
  ctx.globalAlpha = 1;
  return { skeletons: bodies.length, discs, probe };
}

// One player enlarged in his own frame, centred on the centroid of his joints, over a grid on
// the horizontal plane through that centroid (the only z the README vouches for, limit 2):
// no floor, no vertical scale. Without a pose in the frame he is the replay's disc.
export function drawFollow(
  ctx: CanvasRenderingContext2D,
  clip: PoseClip,
  entry: PlayerAt,
  camera: Camera,
): "skeleton" | "disc" {
  const { width, height } = ctx.canvas;
  const [i, , , detected, joints] = entry;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "bold 10px system-ui, sans-serif";
  if (joints === null) {
    drawDisc(ctx, width / 2, height / 2, colorOf(clip, i), String(clip.players[i].number), detected === 1);
    return "disc";
  }

  const n = joints[0].length;
  const c = [0, 1, 2].map((k) => joints[0].reduce((sum, p) => sum + p[k], 0) / n / 100);
  const scale = Math.min(width, height) / FOLLOW_SPAN_M;
  const toPixel = ([u, v]: Projected): [number, number] => [width / 2 + u * scale, height / 2 - v * scale];

  ctx.strokeStyle = COLORS.surface;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.5;
  const steps = Math.round(GRID_HALF_M / GRID_STEP_M);
  for (let k = -steps; k <= steps; k++) {
    const s = k * GRID_STEP_M;
    for (const [a, b] of [
      [project(s, -GRID_HALF_M, 0, camera), project(s, GRID_HALF_M, 0, camera)],
      [project(-GRID_HALF_M, s, 0, camera), project(GRID_HALF_M, s, 0, camera)],
    ]) {
      const [ax, ay] = toPixel(a);
      const [bx, by] = toPixel(b);
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;

  const points = joints[0].map(([dx, dy, dz]) =>
    project(dx / 100 - c[0], dy / 100 - c[1], dz / 100 - c[2], camera),
  );
  strokeSkeleton(ctx, clip, joints, points, toPixel, colorOf(clip, i), FOLLOW_BONE_PX, FOLLOW_JOINT_PX);
  return "skeleton";
}
