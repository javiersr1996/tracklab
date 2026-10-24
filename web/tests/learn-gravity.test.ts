import { describe, expect, it } from "vitest";
import fence from "../lib/learn/fence.json";
import {
  analyticSdG,
  apparentG,
  countBelow,
  fitQuadratic,
  gAtHalfWindow,
  heightScaleNeeded,
  rmsAt,
  roundingBound,
  signTest,
  timeScaleNeeded,
  withNoise,
} from "../lib/learn/gravity";
import { GRAVITY_HOOK, GRAVITY_MATCHES, HOOK_Z_HALF_UNIT_M } from "../lib/learn/gravity-data";
import { CHECKS } from "../lib/quality";

// Lesson 1's arithmetic (task 77) against synthetic flights with a known g and against P3's own
// artefact, `quality.json`: its hook flight (21 samples at 4 decimals, the g P3 fitted to them
// before rounding, and the same flight redrawn at `g_real`) and its per-match gravity rows. Every
// figure of the file is read from it; G is the hook's `g_real`.
//
// Mutations checked by hand, each restored byte for byte (the task's four first):
// - g = −a in `apparentG`: g comes out halved, and "is exact on a parabola", "within the rounding
//   bound" (both), "half-window 10", "rmsAt least" and "over 200 seeds" fail.
// - Time not centred in `fitQuadratic` (t0 = 0): fine at origin 0, off by 3e-5 at −12.5 s and ~0
//   instead of G at 3600 s; "is exact on a parabola ... at any time origin" fails.
// - Football let through `basketballGravity`: the pivot throws on import (football has no
//   `is_calibration` row); with that guard dropped too, 30 rows fail "keep the ten basketball
//   matches" and the Q3 count gives 27.
// - Noise without zero mean: |N(0, 1)| (mean 0.80σ, sd 0.60σ) leaves the mean of g alone and fails
//   the sd at 0.60 of 2σ/√Σw²; N(0, 1) + 1 moves neither the mean nor the sd of g (c takes it) and
//   fails the draws' own mean, 0.0099 m against 0.00046.
// - Also: w = u² without − m (four fail, the closed form among them), the sign test's tail from
//   j > k (both sign tests), 1 − g/G as the time scale (the scales), the bound without its 2
//   (worst rounding) and g instead of g/2 in `residualsAt` (rmsAt least).

const { t_s: t, z_data_m: zData, z_real_m: zReal, g_data: gData, g_real: G } = GRAVITY_HOOK;

const mean = (xs: readonly number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;
const sd = (xs: readonly number[]) => {
  const m = mean(xs);
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / (xs.length - 1));
};
const near = (x: number, want: number, rel: number) => Math.abs(x - want) <= rel * Math.max(1, Math.abs(want));

// 21 samples at 25 fps around `origin` of a flight falling at G, its vertex 13 ms after the middle
// sample and moving up 1.3 m/s there: c, b and a all matter, in t's own origin.
function flight(origin: number) {
  const apex = origin + 0.013;
  const times = Array.from({ length: 21 }, (_, k) => origin + (k - 10) / 25);
  const heights = times.map((ti) => 4.5 + 1.3 * (ti - apex) - (G / 2) * (ti - apex) ** 2);
  return { times, heights, c: 4.5 - 1.3 * apex - (G / 2) * apex ** 2, b: 1.3 + G * apex, a: -G / 2 };
}

describe("the fit", () => {
  it("is exact on a parabola, general and closed form, at any time origin", () => {
    for (const origin of [0, -12.5, 3600]) {
      const f = flight(origin);
      const q = fitQuadratic(f.times, f.heights);
      const fits = [near(q.c, f.c, 1e-9), near(q.b, f.b, 1e-9), near(q.a, f.a, 1e-9)];
      expect(fits).toEqual([true, true, true]);
      expect(Math.abs(apparentG(f.times, f.heights) - G)).toBeLessThan(1e-9);
      for (let h = 1; h <= 10; h++) {
        expect(Math.abs(gAtHalfWindow(f.times, f.heights, h) - G)).toBeLessThan(1e-9);
      }
    }
  });

  it("moves g by at most the rounding bound, and the worst rounding reaches it", () => {
    const f = flight(0);
    const exact = apparentG(f.times, f.heights);
    const bound = roundingBound(f.times, HOOK_Z_HALF_UNIT_M);
    const rounded = f.heights.map((z) => Math.round(z * 1e4) / 1e4);
    expect(Math.abs(apparentG(f.times, rounded) - exact)).toBeLessThanOrEqual(bound);
    // Each error at half a unit with the sign of u² − m, u the centred time and m its mean square.
    const u = f.times.map((ti) => ti - mean(f.times));
    const m = mean(u.map((ui) => ui * ui));
    const worst = f.heights.map((z, i) => z + HOOK_Z_HALF_UNIT_M * Math.sign(u[i] * u[i] - m));
    expect(Math.abs(Math.abs(apparentG(f.times, worst) - exact) - bound)).toBeLessThan(1e-12);
  });
});

describe("the hook flight", () => {
  it("gives back g_data within the rounding bound, and z_real_m gives back g_real", () => {
    // g_data is itself rounded to 4 decimals (`publish/quality.py:359`): half a unit more.
    const bound = roundingBound(t, HOOK_Z_HALF_UNIT_M);
    expect(Math.abs(apparentG(t, zData) - gData)).toBeLessThanOrEqual(bound + 0.00005);
    expect(Math.abs(apparentG(t, zReal) - G)).toBeLessThanOrEqual(bound);
  });

  it("has its half-window 10 equal to the general fit to 1e-9", () => {
    expect(Math.abs(gAtHalfWindow(t, zData, 10) - apparentG(t, zData))).toBeLessThan(1e-9);
    expect(Math.abs(gAtHalfWindow(t, zReal, 10) - apparentG(t, zReal))).toBeLessThan(1e-9);
  });

  it("has rmsAt least at the fitted g, where it is the fit's own RMS", () => {
    const g = apparentG(t, zData);
    const best = rmsAt(t, zData, g);
    for (const d of [1e-3, 0.1, 1]) {
      expect(rmsAt(t, zData, g - d)).toBeGreaterThan(best);
      expect(rmsAt(t, zData, g + d)).toBeGreaterThan(best);
    }
    const { c, b, a } = fitQuadratic(t, zData);
    const own = Math.sqrt(mean(zData.map((z, i) => (z - (c + b * t[i] + a * t[i] ** 2)) ** 2)));
    expect(Math.abs(best - own)).toBeLessThan(1e-12);
  });

  it("goes back to g_real with its times shrunk or its heights divided by the scale needed", () => {
    const g = apparentG(t, zData);
    const s = timeScaleNeeded(g, G);
    expect(Math.abs(apparentG(t.map((ti) => ti * (1 - s)), zData) - G)).toBeLessThan(1e-9);
    const k = heightScaleNeeded(g, G);
    expect(Math.abs(apparentG(t, zData.map((z) => z / k)) - G)).toBeLessThan(1e-9);
  });
});

describe("noise on z_real_m", () => {
  it("over 200 seeds at 1 cm: mean g within 3 sd/√N of g_real, sd within 10 % of 2σ/√Σw²", () => {
    const N = 200;
    const sigma = 0.01;
    const gs: number[] = [];
    const draws: number[] = [];
    for (let seed = 1; seed <= N; seed++) {
      const z = withNoise(zReal, sigma, seed);
      gs.push(apparentG(t, z));
      draws.push(...z.map((zi, i) => zi - zReal[i]));
    }
    const analytic = analyticSdG(t, sigma);
    expect(Math.abs(mean(gs) - G)).toBeLessThan((3 * analytic) / Math.sqrt(N));
    expect(Math.abs(sd(gs) / analytic - 1)).toBeLessThan(0.1);
    // A shift common to every sample goes into c and leaves g alone: only the draws show it.
    expect(Math.abs(mean(draws))).toBeLessThan((3 * sigma) / Math.sqrt(draws.length));
  });

  it("is the same for the same seed and different for another", () => {
    expect(withNoise(zReal, 0.01, 7)).toEqual(withNoise(zReal, 0.01, 7));
    expect(withNoise(zReal, 0.01, 8)).not.toEqual(withNoise(zReal, 0.01, 7));
  });
});

describe("the sign test", () => {
  it("is the binomial tail of k or more below, 2⁻ⁿ when k = n, ties left out", () => {
    expect(signTest([1, 2, 3, 5], 4)).toEqual({ k: 3, n: 4, p: 5 / 16 });
    expect(signTest([1, 4, 5], 4)).toEqual({ k: 1, n: 2, p: 3 / 4 });
    expect(signTest([1, 2, 3], 4)).toEqual({ k: 3, n: 3, p: 2 ** -3 });
  });
});

describe("the basketball rows of quality.json", () => {
  it("keep the ten basketball matches and no football row, held-out ids included", () => {
    expect(CHECKS.gravity.some((r) => r.sport === "football")).toBe(true);
    expect(GRAVITY_MATCHES).toHaveLength(10);
    expect(GRAVITY_MATCHES.every((r) => r.match_id.startsWith("bb:"))).toBe(true);
    const out = JSON.stringify({ GRAVITY_MATCHES, GRAVITY_HOOK });
    expect(fence.held_out.filter((id) => out.includes(id))).toEqual([]);
  });

  it("carry each match's figures as the file has them", () => {
    const file = (id: string, metric: string) =>
      CHECKS.gravity.find((r) => r.match_id === id && r.metric === metric)?.value;
    for (const r of GRAVITY_MATCHES) {
      expect([r.flights, r.g_median, r.g_q1, r.g_q3, r.is_calibration]).toEqual([
        file(r.match_id, "flights"),
        file(r.match_id, "g_median"),
        file(r.match_id, "g_q1"),
        file(r.match_id, "g_q3"),
        file(r.match_id, "is_calibration") === 1,
      ]);
    }
  });

  it("have Q3 below g_real in 10 of 10, and the medians all below it at p = 2⁻¹⁰", () => {
    expect(countBelow(GRAVITY_MATCHES.map((r) => r.g_q3), G)).toBe(10);
    expect(signTest(GRAVITY_MATCHES.map((r) => r.g_median), G)).toEqual({ k: 10, n: 10, p: 2 ** -10 });
  });
});
