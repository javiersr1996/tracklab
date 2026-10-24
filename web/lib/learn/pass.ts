// Lesson 7's arithmetic: a pass measured by the ball itself. The chord is the ball's displacement
// from where it is at the pass's first frame to where it is at its last; the path adds up every
// step in between, so it can never be shorter than the chord.
export type Point3 = readonly [number, number, number];

export const chord = (a: Point3, b: Point3): number => Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);

export function path(points: readonly Point3[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += chord(points[i - 1], points[i]);
  return total;
}

// A length covered in `frames` frames at `fps`, per second.
export const perSecond = (length: number, frames: number, fps: number): number => length / (frames / fps);
