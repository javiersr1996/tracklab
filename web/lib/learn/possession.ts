// Lesson 10's arithmetic: durations as a distribution. Pure functions over arrays of seconds;
// nothing here reads a file.

// The q-quantile by linear interpolation between order statistics, as DuckDB's `quantile_cont`
// and numpy's default: position (n − 1)·q in the sorted values.
export function quantile(xs: readonly number[], q: number): number {
  const a = [...xs].sort((x, y) => x - y);
  const pos = (a.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, a.length - 1);
  return a[lo] + (pos - lo) * (a[hi] - a[lo]);
}

// The empirical survival function: the share of durations longer than t.
export const survival = (xs: readonly number[], t: number): number => xs.filter((x) => x > t).length / xs.length;

// The exponential survival function with median m: half the durations outlive m, a quarter 2m,
// whatever has already elapsed (a constant chance per second of the run ending).
export const expSurvival = (m: number, t: number): number => 2 ** (-t / m);

// The exponential's q-quantile over its median: log2(1 / (1 − q)), whatever the median.
export const expRatio = (q: number): number => Math.log2(1 / (1 - q));
