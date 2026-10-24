// The arithmetic of lesson 4 (`/learn/rebound`), with no data and no DOM: each player's time to
// arrive at a point, who is nearest, who arrives first, and the chance each is first when every
// arrival time is logistic around its value. It mirrors `pipeline/src/tracklab/learn/rebound.py`
// (`arrival`, `nearest`, `first`, `chance_first`). Metres, seconds and m/s throughout.

export interface Runner {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export type Point = readonly number[]; // [x, y]

// The integral of `chanceFirst` runs over ±GRID logistic scales around the earliest time, in steps
// of STEP scales: the pipeline's grid, so the two agree to the published decimals.
const GRID = 40;
const STEP = 0.02;

// The index of the smallest value; the first on a tie, like numpy's argmin.
export function argmin(xs: readonly number[]): number {
  let best = 0;
  for (let i = 1; i < xs.length; i++) if (xs[i] < xs[best]) best = i;
  return best;
}

export const distance = (r: Runner, target: Point) => Math.hypot(target[0] - r.x, target[1] - r.y);

// For `reaction` seconds the player carries the velocity they have; the rest of the way is run at
// `topSpeed`.
export function arrival(runners: readonly Runner[], target: Point, reaction: number, topSpeed: number): number[] {
  return runners.map((r) => reaction + Math.hypot(target[0] - r.x - r.vx * reaction, target[1] - r.y - r.vy * reaction) / topSpeed);
}

export const nearest = (runners: readonly Runner[], target: Point) => argmin(runners.map((r) => distance(r, target)));

// The logistic's scale for a standard deviation `spread`: its sd is scale · π / √3.
export const logisticScale = (spread: number) => (Math.sqrt(3) * spread) / Math.PI;

// The chance a player has arrived by time t when the arrival is logistic around `time`
// (Spearman's equation 4), written with tanh so it neither overflows nor divides by zero.
export const arrivedBy = (t: number, time: number, spread: number) => 0.5 * (1 + Math.tanh((t - time) / logisticScale(spread) / 2));

// The chance each player is first: the integral over t of one player's density times every other
// player's chance of not having arrived yet.
export function chanceFirst(times: readonly number[], spread: number): number[] {
  const scale = logisticScale(spread);
  const t0 = Math.min(...times);
  const steps = Math.round((2 * GRID) / STEP);
  const out = times.map(() => 0);
  for (let k = 0; k <= steps; k++) {
    const t = t0 + scale * (-GRID + k * STEP);
    const arrived = times.map((time) => 0.5 * (1 + Math.tanh((t - time) / scale / 2)));
    for (let i = 0; i < times.length; i++) {
      let others = 1;
      for (let j = 0; j < times.length; j++) if (j !== i) others *= 1 - arrived[j];
      out[i] += ((arrived[i] * (1 - arrived[i])) / scale) * others;
    }
  }
  return out.map((v) => v * STEP * scale);
}
