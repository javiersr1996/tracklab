// The viewer's own projection (decision 1 of P6): an orthographic camera turned by `yaw` about
// the vertical axis and tipped by `tilt` away from looking straight down. Pure functions, no
// canvas, so the tests can hold them.
//
// Output: u to the right, v up, depth away from the camera (larger is farther), all in the
// units of the input. With tilt 0 the camera looks straight down: z drops out and (u, v) is
// (x, y) turned by yaw, which at yaw 0 is how the replay draws the pitch. With tilt 90 it looks
// level, towards +y turned by yaw, and v is z.

export interface Camera {
  yaw: number; // degrees
  tilt: number; // degrees, 0 straight down, 90 level
}

export type Projected = [u: number, v: number, depth: number];

export function project(x: number, y: number, z: number, camera: Camera): Projected {
  const yaw = (camera.yaw * Math.PI) / 180;
  const tilt = (camera.tilt * Math.PI) / 180;
  const xr = x * Math.cos(yaw) - y * Math.sin(yaw);
  const yr = x * Math.sin(yaw) + y * Math.cos(yaw);
  return [xr, yr * Math.cos(tilt) + z * Math.sin(tilt), yr * Math.sin(tilt) - z * Math.cos(tilt)];
}

// Bones in painting order: the farthest first (by the mean depth of its two ends), so a nearer
// bone is drawn over a farther one.
export function byDepth(points: Projected[], bones: [number, number][]): [number, number][] {
  const depth = ([a, b]: [number, number]) => points[a][2] + points[b][2];
  return [...bones].sort((p, q) => depth(q) - depth(p));
}
