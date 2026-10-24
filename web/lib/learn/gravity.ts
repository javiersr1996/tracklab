// The arithmetic of lesson 1 (`/learn/gravity`, task 77), with no data and no DOM: the
// least-squares parabola z(t) = c + b·t + a·t² a ball's height is fitted with, g = −2a, and what
// moves that g (the window, noise, rounding, a rescaled clock or height). The general fit mirrors
// `pipeline/src/tracklab/quality/flight.py` (`fit_quadratic`, `apparent_g`); the samples come from
// `gravity-data.ts` or are synthetic with a seed. Metres and seconds throughout.

export interface Quadratic {
  c: number;
  b: number;
  a: number;
}

const sum = (xs: readonly number[]): number => xs.reduce((s, x) => s + x, 0);

// t minus its mean: the normal equations stay well conditioned at any absolute t.
function centred(t: readonly number[]): number[] {
  const t0 = sum(t) / t.length;
  return t.map((ti) => ti - t0);
}

// (c, b, a) of the least-squares z = c + b·t + a·t², by Cramer's rule on the normal equations in
// centred time, then moved back to t's own origin (`flight.py:19-40`).
export function fitQuadratic(t: readonly number[], z: readonly number[]): Quadratic {
  const n = t.length;
  if (n < 3 || n !== z.length) {
    throw new RangeError(`need at least 3 paired samples, got ${n} and ${z.length}`);
  }
  const t0 = sum(t) / n;
  const u = t.map((ti) => ti - t0);
  const [s1, s2, s3, s4] = [1, 2, 3, 4].map((k) => sum(u.map((ui) => ui ** k)));
  const y = [sum(z), sum(u.map((ui, i) => ui * z[i])), sum(u.map((ui, i) => ui * ui * z[i]))];
  const m = [
    [n, s1, s2],
    [s1, s2, s3],
    [s2, s3, s4],
  ];
  const det = det3(m);
  if (Math.abs(det) < 1e-12) {
    throw new RangeError("degenerate window: the samples do not span three times");
  }
  const withColumn = (j: number) => m.map((row, i) => row.map((v, k) => (k === j ? y[i] : v)));
  const [c, b, a] = [0, 1, 2].map((j) => det3(withColumn(j)) / det);
  // Back from centred time: z = c + b(t − t0) + a(t − t0)².
  return { c: c - b * t0 + a * t0 * t0, b: b - 2 * a * t0, a };
}

function det3(m: number[][]): number {
  return (
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  );
}

// The g a flight implies, positive for a ball that falls.
export const apparentG = (t: readonly number[], z: readonly number[]): number => -2 * fitQuadratic(t, z).a;

// The closed form on a window symmetric about its middle: there the odd sums of u vanish and
// a = Σw·z / Σw², with w = u² − m and m the mean of u² (the form `gravity.sql` computes).
function curvatureWeights(t: readonly number[]): { w: number[]; ww: number } {
  const u = centred(t);
  const m = sum(u.map((ui) => ui * ui)) / u.length;
  const w = u.map((ui) => ui * ui - m);
  return { w, ww: sum(w.map((wi) => wi * wi)) };
}

// g over the 2h + 1 samples centred on the middle one of an odd window (the apex of a published
// flight), by the closed form; h runs from 1 (three samples, an exact fit) to the whole window.
export function gAtHalfWindow(t: readonly number[], z: readonly number[], h: number): number {
  const mid = (t.length - 1) / 2;
  if (!Number.isInteger(mid) || t.length !== z.length || !Number.isInteger(h) || h < 1 || h > mid) {
    throw new RangeError(`half-window ${h} does not fit ${t.length} samples`);
  }
  const keep = <T>(xs: readonly T[]) => xs.slice(mid - h, mid + h + 1);
  const { w, ww } = curvatureWeights(keep(t));
  const zs = keep(z);
  return (-2 * sum(w.map((wi, i) => wi * zs[i]))) / ww;
}

// The parabola that falls with g held, c and b fitted: in centred time that is a straight line
// through z + g·u²/2, whose least squares are its mean and its slope.
function heldG(t: readonly number[], z: readonly number[], g: number) {
  const u = centred(t);
  const lifted = z.map((zi, i) => zi + 0.5 * g * u[i] * u[i]);
  const c = sum(lifted) / lifted.length;
  const b = sum(u.map((ui, i) => ui * lifted[i])) / sum(u.map((ui) => ui * ui));
  return { u, lifted, c, b };
}

// The residuals of z against that parabola.
export function residualsAt(t: readonly number[], z: readonly number[], g: number): number[] {
  const { u, lifted, c, b } = heldG(t, z, g);
  return lifted.map((li, i) => li - c - b * u[i]);
}

// The same parabola as (c, b, a) in t's own origin, to draw it between the samples.
export function fitAtG(t: readonly number[], z: readonly number[], g: number): Quadratic {
  const { c, b } = heldG(t, z, g);
  const t0 = sum(t) / t.length;
  const a = -0.5 * g;
  // Back from centred time: z = c + b(t − t0) + a(t − t0)².
  return { c: c - b * t0 + a * t0 * t0, b: b - 2 * a * t0, a };
}

// Root mean square of `residualsAt`, over n like P3's residual cut (`gravity.py:_fit_or_drop`).
export function rmsAt(t: readonly number[], z: readonly number[], g: number): number {
  const r = residualsAt(t, z, g);
  return Math.sqrt(sum(r.map((ri) => ri * ri)) / r.length);
}

// The sd of the closed-form g when every z carries independent noise of sd sigma: g = −2·Σw·z/Σw²,
// so sd(g) = 2σ/√Σw².
export function analyticSdG(t: readonly number[], sigma: number): number {
  return (2 * sigma) / Math.sqrt(curvatureWeights(t).ww);
}

// The most that rounding every z to within ±halfUnit can move the closed-form g:
// 2·halfUnit·Σ|w|/Σw², reached when each error takes the sign of its w.
export function roundingBound(t: readonly number[], halfUnit: number): number {
  const { w, ww } = curvatureWeights(t);
  return (2 * halfUnit * sum(w.map(Math.abs))) / ww;
}

// mulberry32: a 32-bit generator, uniform on [0, 1), so a seed always gives the same flights.
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let x = Math.imul(state ^ (state >>> 15), state | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// A standard normal draw by Box-Muller (1 − u keeps the logarithm finite).
export function gaussian(rng: () => number): number {
  const u1 = 1 - rng();
  const u2 = rng();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

// z plus independent normal noise of sd sigma, drawn from `seed`.
export function withNoise(z: readonly number[], sigma: number, seed: number): number[] {
  const rng = mulberry32(seed);
  return z.map((zi) => zi + sigma * gaussian(rng));
}

export const countBelow = (values: readonly number[], ref: number): number =>
  values.filter((v) => v < ref).length;

// One-sided sign test of "below ref": k of the n values fall below it, and p is the chance of k or
// more under a fair coin, Σ_{j≥k} C(n, j)/2ⁿ, which is 2⁻ⁿ when k = n. A value equal to ref has
// no sign and is left out of n.
export function signTest(values: readonly number[], ref: number): { k: number; n: number; p: number } {
  const n = values.filter((v) => v !== ref).length;
  const k = countBelow(values, ref);
  let choose = 1; // C(n, j), starting at j = 0
  let tail = 0;
  for (let j = 0; j <= n; j++) {
    if (j >= k) tail += choose;
    choose = (choose * (n - j)) / (j + 1);
  }
  return { k, n, p: tail / 2 ** n };
}

// What would turn a measured g back into G, one cause at a time. g goes as height over time
// squared: the flight's times would have to shrink by 1 − √(g/G), or its heights be divided by g/G.
export const timeScaleNeeded = (g: number, G: number): number => 1 - Math.sqrt(g / G);
export const heightScaleNeeded = (g: number, G: number): number => g / G;
