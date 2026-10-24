// Lesson 6's arithmetic: a line through two clocks. The fit is about the mean time, so the
// intercept it gives is the clock at the middle of the fitted frames, not at the start of the
// video; the slope does not depend on that choice, the sums do (`tracklab.learn.clock.slope`).

export interface LineFit {
  slope: number;
  // The fitted clock at `tMean`: with a centred fit, the mean of the clock.
  atMean: number;
  tMean: number;
  n: number;
}

export function fitLine(t: readonly number[], y: readonly number[]): LineFit {
  const n = t.length;
  if (n < 2 || y.length !== n) throw new Error("a line needs two samples or more, as many times as values");
  const tMean = t.reduce((s, v) => s + v, 0) / n;
  const yMean = y.reduce((s, v) => s + v, 0) / n;
  let sxy = 0;
  let sxx = 0;
  for (let i = 0; i < n; i++) {
    const dt = t[i] - tMean;
    sxy += dt * (y[i] - yMean);
    sxx += dt * dt;
  }
  if (sxx === 0) throw new Error("every sample at the same time");
  return { slope: sxy / sxx, atMean: yMean, tMean, n };
}

export const lineAt = (fit: LineFit, t: number): number => fit.atMean + fit.slope * (t - fit.tMean);

export const residuals = (t: readonly number[], y: readonly number[], fit: LineFit): number[] => t.map((ti, i) => y[i] - lineAt(fit, ti));

export const rms = (xs: readonly number[]): number => Math.sqrt(xs.reduce((s, v) => s + v * v, 0) / xs.length);

// The last sample still at the clock's value at `from`: from there on the clock moves.
export function firstMove(y: readonly number[], from = 0): number {
  for (let i = from + 1; i < y.length; i++) if (y[i] !== y[from]) return i - 1;
  return y.length - 1;
}

// What a scale on the video's clock does. g is a length over a time squared: if every second of
// video were `s` true seconds, a g measured in video seconds would be g / s² in true ones.
export const gInSeconds = (g: number, s: number): number => g / (s * s);
// The scale that turns a measured g into G, and the slope a true clock would then show against
// the video's (counting down): −√(g/G).
export const scaleForG = (g: number, G: number): number => Math.sqrt(g / G);
export const slopeForG = (g: number, G: number): number => -scaleForG(g, G);
