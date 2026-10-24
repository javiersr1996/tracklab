// Lesson 9's arithmetic: dribbles as points in time, and the ball's height as a signal. Pure
// functions over arrays indexed by frame; nothing here reads a file.
import { autocorrelation, firstPeak, type Peak } from "./cadence";

// The gaps between consecutive events, in frames.
export function intervals(frames: readonly number[]): number[] {
  return frames.slice(1).map((f, i) => f - frames[i]);
}

// The offset from frame `at` to the lowest height within `reach` frames either side, ties to the
// earliest frame, and that height; null when a frame of the window has no height. `z[i]` is the
// height at frame `first + i`.
export function lowest(z: readonly (number | null)[], first: number, at: number, reach: number): { k: number; z: number } | null {
  let best: { k: number; z: number } | null = null;
  for (let k = -reach; k <= reach; k++) {
    const h = z[at + k - first];
    if (h === null || h === undefined) return null;
    if (best === null || h < best.z) best = { k, z: h };
  }
  return best;
}

// The frames where the height is lower than the frame before and no higher than the frame after:
// each run of equal lows counts once, at its first frame.
export function lowPoints(z: readonly number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < z.length - 1; i++) if (z[i] < z[i - 1] && z[i] <= z[i + 1]) out.push(i);
  return out;
}

// The rhythm of the height itself: the first peak of its autocorrelation after it turns negative
// (lesson 5's reading), with the parabola's shift; its lag in frames is the signal's period.
export function rhythm(z: readonly number[]): (Peak & { lag: number }) | null {
  const peak = firstPeak(autocorrelation(z));
  return peak ? { ...peak, lag: peak.k + peak.shift } : null;
}
