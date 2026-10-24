// The arithmetic of lesson 2 (`/learn/speed`), with no data and no DOM: finite differences of a
// player's positions, a moving average of them, a Savitzky-Golay filter of order one, and the
// gap between an estimate and the provider's speed. It mirrors `pipeline/src/tracklab/learn/
// speed.py` (`difference`, `smoothed`, `estimate`); the samples come from `speed-data.ts` or are
// synthetic. Metres, seconds and m/s throughout.

export type Kind = "forward" | "backward" | "central";

// Frame offset -> weight on the position at that offset; the velocity is the weighted sum.
export type Weights = ReadonlyMap<number, number>;

// The difference from `before` frames back to `after` frames ahead, per second.
function difference(after: number, before: number, h: number): Weights {
  const span = (after + before) * h;
  return new Map([
    [-before, -1 / span],
    [after, 1 / span],
  ]);
}

export function differenceWeights(kind: Kind, h: number): Weights {
  if (kind === "forward") return difference(1, 0, h);
  if (kind === "backward") return difference(0, 1, h);
  return difference(1, 1, h);
}

// A centred moving average of k (odd) copies of a difference. The weights add up offset by
// offset, the inner positions cancel, and what is left is one longer difference.
export function smoothed(weights: Weights, k: number): Weights {
  if (k < 1 || k % 2 === 0) throw new RangeError(`the window must be odd, got ${k}`);
  const half = (k - 1) / 2;
  const out = new Map<number, number>();
  for (let j = -half; j <= half; j++) {
    for (const [o, w] of weights) out.set(o + j, (out.get(o + j) ?? 0) + w / k);
  }
  return new Map([...out].filter(([, w]) => Math.abs(w) > 1e-12).sort(([a], [b]) => a - b));
}

// The speed the weights give at every frame, or null where an offset falls outside the track.
export function estimate(x: readonly number[], y: readonly number[], weights: Weights): (number | null)[] {
  const offsets = [...weights.keys()];
  const lo = Math.min(...offsets);
  const hi = Math.max(...offsets);
  return x.map((_, i) => {
    if (i + lo < 0 || i + hi >= x.length) return null;
    let vx = 0;
    let vy = 0;
    for (const [o, w] of weights) {
      vx += w * x[i + o];
      vy += w * y[i + o];
    }
    return Math.hypot(vx, vy);
  });
}

export function median(xs: readonly number[]): number {
  if (xs.length === 0) throw new RangeError("median of nothing");
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 === 1 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export interface Gap {
  frames: number;
  median: number;
  max: number;
  gaps: (number | null)[]; // speed minus estimate, frame by frame
}

// |speed − estimate| over the frames where the estimate exists.
export function gapTo(speed: readonly number[], est: readonly (number | null)[]): Gap {
  const gaps = est.map((e, i) => (e === null ? null : speed[i] - e));
  const abs = gaps.filter((g): g is number => g !== null).map(Math.abs);
  return { frames: abs.length, median: median(abs), max: Math.max(...abs), gaps };
}

// The largest error the rounding of every position to `resolution` can put in one axis of the
// velocity: each position is off by half a unit at most, in whichever direction hurts.
export function roundingBound(weights: Weights, resolution: number): number {
  return [...weights.values()].reduce((s, w) => s + Math.abs(w), 0) * (resolution / 2);
}

// A Savitzky-Golay filter: at every sample, the least-squares polynomial of `order` through the
// k samples around it, evaluated at the middle one. Solved by the normal equations in centred
// time; the first and last (k − 1) / 2 samples are left null.
export function savitzkyGolay(values: readonly number[], k: number, order: number): (number | null)[] {
  const half = (k - 1) / 2;
  const u = Array.from({ length: k }, (_, j) => j - half);
  const n = order + 1;
  const a = Array.from({ length: n }, (_, r) => Array.from({ length: n }, (_, c) => u.reduce((s, uj) => s + uj ** (r + c), 0)));
  return values.map((_, i) => {
    if (i < half || i + half >= values.length) return null;
    const b = Array.from({ length: n }, (_, r) => u.reduce((s, uj, j) => s + uj ** r * values[i - half + j], 0));
    return solve(a, b)[0]; // the constant term: the polynomial's value at u = 0
  });
}

// Gaussian elimination with partial pivoting, for the small systems above.
function solve(a: readonly number[][], b: readonly number[]): number[] {
  const n = b.length;
  const m = a.map((row, r) => [...row, b[r]]);
  for (let c = 0; c < n; c++) {
    const p = m.reduce((best, row, r) => (r >= c && Math.abs(row[c]) > Math.abs(m[best][c]) ? r : best), c);
    [m[c], m[p]] = [m[p], m[c]];
    for (let r = c + 1; r < n; r++) {
      const f = m[r][c] / m[c][c];
      for (let k = c; k <= n; k++) m[r][k] -= f * m[c][k];
    }
  }
  const out = Array<number>(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    out[r] = (m[r][n] - m[r].slice(r + 1, n).reduce((s, v, j) => s + v * out[r + 1 + j], 0)) / m[r][r];
  }
  return out;
}

// A centred moving average of k (odd); null where the window leaves the series.
export function movingAverage(values: readonly number[], k: number): (number | null)[] {
  const half = (k - 1) / 2;
  return values.map((_, i) => {
    if (i < half || i + half >= values.length) return null;
    let s = 0;
    for (let j = i - half; j <= i + half; j++) s += values[j];
    return s / k;
  });
}

// Positions of a body at constant acceleration a from rest, one per step h: a parabola in time.
export function parabolaPath(a: number, h: number, frames: number): number[] {
  return Array.from({ length: frames }, (_, i) => 0.5 * a * (i * h) ** 2);
}
