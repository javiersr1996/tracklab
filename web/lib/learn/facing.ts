// Lesson 11's arithmetic: a direction as an angle. The facing of a player is the normal to the
// line from the right shoulder to the left one, on the side of the nose; the heading is the
// central difference of the player's x, y; the relative angle is their difference on the circle;
// and the mean and variance of angles are the circular ones. Degrees everywhere; pure functions
// over numbers and arrays, nothing here reads a file. `pipeline/src/tracklab/learn/facing.py`
// takes the same steps on the published clip, and `facing.browser.sql` in the browser.
import { median } from "./cadence";

export const MIN_SPEED_M_S = 2; // a frame counts only when the player moves faster than this
export const MIN_FRAMES = 25; // a player counts only with this many such frames
export const SIDE_DEG = 45; // |relative| past this: side on, or further round
export const BACK_DEG = 135; // past this: the back to the direction of travel

export type XY = readonly [number, number];
const DEG = 180 / Math.PI;

// An angle brought into (−180, 180].
export const wrap = (deg: number): number => 180 - ((((180 - deg) % 360) + 360) % 360);

// The normal to the shoulder line on the nose's side, in degrees from the x axis. The line runs
// from the right shoulder to the left; of its two normals the one whose dot product with the
// nose's offset from the shoulders' midpoint is positive is the facing, brought into (−180, 180]
// (a shoulder line along y gives −sx = −0, and atan2 would answer −180 for 180). NaN when the
// shoulders coincide or the nose lies on their line: neither normal is the nose's.
export function facingDeg(left: XY, right: XY, nose: XY): number {
  const sx = left[0] - right[0];
  const sy = left[1] - right[1];
  const nx = nose[0] - (left[0] + right[0]) / 2;
  const ny = nose[1] - (left[1] + right[1]) / 2;
  const side = sy * nx - sx * ny; // the normal (sy, −sx) against the nose
  if (side === 0) return NaN;
  return wrap(side > 0 ? Math.atan2(-sx, sy) * DEG : Math.atan2(sx, -sy) * DEG);
}

// The direction of travel from the frame before to the frame after (lesson 2's central
// difference, which the step cancels out of), in degrees from the x axis.
export const headingDeg = (before: XY, after: XY): number => Math.atan2(after[1] - before[1], after[0] - before[0]) * DEG;

// The speed over the same two frames: their distance over twice the frame step.
export const centralSpeed = (before: XY, after: XY, dt: number): number => Math.hypot(after[0] - before[0], after[1] - before[1]) / (2 * dt);

// Facing minus heading, on the circle.
export const relativeDeg = (facing: number, heading: number): number => wrap(facing - heading);

export interface Circular {
  mean: number; // the argument of the mean resultant vector, in degrees
  resultant: number; // its length, 0 to 1
}

// The mean resultant vector of angles: the average of their unit vectors. Its argument is the
// circular mean and its length says how far the angles agree (1: all the same; 0: no direction).
export function circular(deg: readonly number[]): Circular {
  const c = deg.reduce((a, v) => a + Math.cos(v / DEG), 0) / deg.length;
  const s = deg.reduce((a, v) => a + Math.sin(v / DEG), 0) / deg.length;
  return { mean: Math.atan2(s, c) * DEG, resultant: Math.hypot(s, c) };
}

// One minus the mean resultant length.
export const circularVariance = (deg: readonly number[]): number => 1 - circular(deg).resultant;

export interface FrameFacing {
  f: number;
  speed: number; // m/s, over the central difference
  facing: number;
  heading: number;
  relative: number;
}

export interface FacingSummary {
  frames: number;
  median_abs: number; // the median of |relative|
  circ_mean: number;
  resultant: number;
  circ_var: number;
  off_pct: number; // |relative| over SIDE_DEG
  back_pct: number; // |relative| over BACK_DEG
}

export function summarise(frames: readonly FrameFacing[]): FacingSummary {
  const rel = frames.map((x) => x.relative);
  const { mean, resultant } = circular(rel);
  return {
    frames: rel.length,
    median_abs: median(rel.map(Math.abs)),
    circ_mean: mean,
    resultant,
    circ_var: 1 - resultant,
    off_pct: (100 * rel.filter((a) => Math.abs(a) > SIDE_DEG).length) / rel.length,
    back_pct: (100 * rel.filter((a) => Math.abs(a) > BACK_DEG).length) / rel.length,
  };
}
