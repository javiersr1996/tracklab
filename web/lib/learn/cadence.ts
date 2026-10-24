// The arithmetic of lesson 5: the cadence of one window of s(t), read from its autocorrelation
// the way `pipeline/src/tracklab/pose/gait.py` reads it (`cadence_hz`), and the sd that the
// ankles' predicted error gives it, to first order and by Monte Carlo. Metres and seconds; pure
// functions over arrays, nothing here reads a file.
import { gaussian, mulberry32 } from "./gravity";

// The two-sided 95 % normal quantile of white noise's band, `BAND_Z` in gait.py.
export const BAND_Z = 1.96;

// r[k] for k = 0 .. n − 1: the products of the centred signal with itself k samples later,
// averaged over their own n − k (gait.py: dividing by n would drag the peak to shorter lags).
export function autocorrelation(s: readonly number[]): number[] {
  const n = s.length;
  const m = s.reduce((a, v) => a + v, 0) / n;
  const s0 = s.map((v) => v - m);
  return Array.from({ length: n }, (_, k) => {
    let sum = 0;
    for (let i = 0; i < n - k; i++) sum += s0[i] * s0[i + k];
    return sum / (n - k);
  });
}

// The white-noise band at lag k of a window of n samples: ±z / √(n − k).
export const band = (n: number, k: number, z = BAND_Z): number => z / Math.sqrt(n - k);

export interface Peak {
  firstNegative: number; // the first lag with r < 0
  k: number; // the first local maximum with r > 0 after it
  shift: number; // the parabola's vertex, in lags, from k
  ratio: number; // r[k] / r[0]
  band: number; // the white-noise band at k
  resolved: boolean; // ratio above the band
}

// The first peak of r after it turns negative, and only that one (gait.py, reading A): null when
// r never turns negative or has no such peak.
export function firstPeak(r: readonly number[], z = BAND_Z): Peak | null {
  const n = r.length;
  if (!(r[0] > 0)) return null;
  const firstNegative = r.findIndex((v) => v < 0);
  if (firstNegative < 0) return null;
  for (let k = firstNegative + 1; k < n - 1; k++) {
    if (r[k] > 0 && r[k] > r[k - 1] && r[k] >= r[k + 1]) {
      const curvature = r[k - 1] - 2 * r[k] + r[k + 1];
      const shift = curvature < 0 ? (0.5 * (r[k - 1] - r[k + 1])) / curvature : 0;
      const ratio = r[k] / r[0];
      const b = band(n, k, z);
      return { firstNegative, k, shift, ratio, band: b, resolved: ratio > b };
    }
  }
  return null;
}

// Steps per second: s(t) swings once per stride, a stride is two steps, so 2 × fps / (k + shift).
// NaN when the first peak is missing or inside the white-noise band.
export function cadenceHz(s: readonly number[], fps: number, z = BAND_Z): number {
  if (s.length < 4 || !s.every(Number.isFinite)) return NaN;
  const p = firstPeak(autocorrelation(s), z);
  return p && p.resolved ? (2 * fps) / (p.k + p.shift) : NaN;
}

// The sd of s at each frame when each ankle is off by N(0, its predicted error) along each axis,
// independently: s is lAnkle − rAnkle along a unit direction, so the variances add.
export const signalSd = (maeLeft: readonly number[], maeRight: readonly number[]): number[] =>
  maeLeft.map((l, i) => Math.hypot(l, maeRight[i]));

// First-order propagation: √Σ (∂c/∂s_i · σ_i)², each derivative by a central difference.
export function linearSd(s: readonly number[], sigma: readonly number[], fps: number, h = 1e-6): number {
  let sum = 0;
  for (let i = 0; i < s.length; i++) {
    const up = s.map((v, j) => (j === i ? v + h : v));
    const down = s.map((v, j) => (j === i ? v - h : v));
    const d = (cadenceHz(up, fps) - cadenceHz(down, fps)) / (2 * h);
    sum += (d * sigma[i]) ** 2;
  }
  return Math.sqrt(sum);
}

// `draws` noisy copies of s, each sample moved by N(0, scale × σ_i), drawn in order from one
// mulberry32 stream: the cadence of each (NaN where it has none). A longer run starts with the
// same draws, so more clicks add dots and keep the ones already there.
export function monteCarlo(s: readonly number[], sigma: readonly number[], fps: number, draws: number, seed: number, scale = 1): number[] {
  const rng = mulberry32(seed);
  return Array.from({ length: draws }, () => cadenceHz(s.map((v, i) => v + scale * sigma[i] * gaussian(rng)), fps));
}

export const mean = (xs: readonly number[]): number => xs.reduce((a, v) => a + v, 0) / xs.length;

export function sd(xs: readonly number[]): number {
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, v) => a + (v - m) ** 2, 0) / (xs.length - 1));
}

export function median(xs: readonly number[]): number {
  const a = [...xs].sort((x, y) => x - y);
  const mid = a.length >> 1;
  return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2;
}
