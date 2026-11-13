// Lesson 3's arithmetic: points in a frame, the affine maps that move them to Pitch & Parquet's common
// frame, and the clocks of two sports on one time axis. Pure functions, no data.

export type Point = readonly [number, number];
export type Matrix = readonly [readonly [number, number], readonly [number, number]];

// One international foot in metres, exact: NIST Guide to the SI, Appendix B.8 (`nist-811-b8` in
// sources.ts), the factor `dim_sport.unit_to_m` carries for basketball.
export const FOOT_M = 0.3048;

export const IDENTITY: Matrix = [
  [1, 0],
  [0, 1],
];
// Half a turn about the origin, the attack normalisation: x and y both change sign.
export const HALF_TURN: Matrix = [
  [-1, 0],
  [0, -1],
];
// A mirror in the y axis: only x changes sign.
export const MIRROR_X: Matrix = [
  [-1, 0],
  [0, 1],
];

export const scaled = (k: number, m: Matrix = IDENTITY): Matrix => [
  [k * m[0][0], k * m[0][1]],
  [k * m[1][0], k * m[1][1]],
];

export const det = (m: Matrix): number => m[0][0] * m[1][1] - m[0][1] * m[1][0];

// p' = A p + b.
export function affine(a: Matrix, b: Point = [0, 0]): (p: Point) => Point {
  return ([x, y]) => [a[0][0] * x + a[0][1] * y + b[0], a[1][0] * x + a[1][1] * y + b[1]];
}

// A provider's point in Pitch & Parquet's frame: to metres by `unitToM`, then turned by the attack sign
// `k` (+1 leaves it, -1 is half a turn). Both providers put the origin at the centre, so b = 0.
export const toCommon = (p: Point, unitToM: number, k: 1 | -1): Point => affine(scaled(k * unitToM))(p);

// The weight of the later sample at time t between samples at ta and tb, as the replay uses it.
export const alphaAt = (ta: number, tb: number, t: number): number => (tb === ta ? 0 : (t - ta) / (tb - ta));

// A figure as the lessons print it: thousands separators from ten thousand up, a minus sign
// rather than a hyphen. The tests strip both before comparing with the source.
export const printed = (v: unknown): string =>
  typeof v === "number" ? (Math.abs(v) >= 10_000 ? v.toLocaleString("en-US") : String(v)).replace("-", "−") : String(v);

// The affine combination of two points with weights 1 - alpha and alpha.
export const lerp = (a: Point, b: Point, alpha: number): Point => [a[0] + (b[0] - a[0]) * alpha, a[1] + (b[1] - a[1]) * alpha];

export function gcd(a: number, b: number): number {
  let [x, y] = [Math.abs(a), Math.abs(b)];
  while (y) [x, y] = [y, x % y];
  return x;
}

export const lcm = (a: number, b: number): number => (a / gcd(a, b)) * b;

// The clocks of two rates on one axis: each one's step in ms, the interval at which both have a
// sample, and how many of one clock's instants in that interval the other has no sample at.
export function sharedClock(rateA: number, rateB: number) {
  const stepA = 1000 / rateA;
  const stepB = 1000 / rateB;
  const shared = lcm(stepA, stepB);
  const everyA = shared / stepA;
  const everyB = shared / stepB;
  return { stepA, stepB, shared, everyA, everyB, missingOnA: everyA - 1, missingOnB: everyB - 1 };
}

// The same half turn for a provider whose origin sat in a corner of an L x W surface: the centred
// point moved by (L/2, W/2). Multiplying by -1 there is not half a turn about the centre; the turn
// that is maps q to (L, W) - q.
export function cornerTurn(p: Point, length: number, width: number) {
  const toCorner = affine(IDENTITY, [length / 2, width / 2]);
  const corner = toCorner(p);
  return {
    corner,
    negated: affine(HALF_TURN)(corner),
    turned: affine(HALF_TURN, [length, width])(corner),
    centred: toCorner(affine(HALF_TURN)(p)),
  };
}

// Inside an L x W surface whose origin is its corner.
export const onCornerSurface = ([x, y]: Point, length: number, width: number) => x >= 0 && x <= length && y >= 0 && y <= width;
