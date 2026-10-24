import { describe, expect, it } from "vitest";
import { HYPOTHESES, type HypothesesFile, hypothesesFigure } from "../lib/learn/hypotheses-data";
import { hypothesesFigures } from "../lib/learn/hypotheses-figures";

// "What the data add" (task 87): the figures the prose computes from gravity.json follow the file,
// and the prose's "no window brings any match back" holds on it.
const mutated = (change: (f: HypothesesFile) => void): HypothesesFile => {
  const copy = structuredClone(HYPOTHESES);
  change(copy);
  return copy;
};

describe("hypothesesFigures", () => {
  it("counts every match's median at every half-window, all of them under standard gravity", () => {
    const f = hypothesesFigures(HYPOTHESES);
    expect(f.cells).toBe(HYPOTHESES.matches.length * HYPOTHESES.half_windows.length);
    expect(f.below).toBe(f.cells);
    expect(f.highest_g).toBeLessThan(HYPOTHESES.g_real);
  });

  it("follows the file: a median above standard gravity is counted and becomes the highest", () => {
    const f = hypothesesFigures(mutated((x) => (x.matches[3].g_median_by_half_window["6"] = 9.9)));
    expect(f.below).toBe(f.cells - 1);
    expect([f.highest_g, f.highest_match, f.highest_h]).toEqual([9.9, HYPOTHESES.matches[3].match_id, 6]);
  });

  it("compares the nearest bin only where it and another bin have flights", () => {
    const base = hypothesesFigures(HYPOTHESES);
    const lower = hypothesesFigures(
      mutated((x) => {
        const m = x.matches.find((r) => r.by_frames_from_start[0].g_median !== null)!;
        m.by_frames_from_start[0].g_median = 1;
      }),
    );
    expect(lower.near_compared).toBe(base.near_compared);
    expect(lower.near_highest).toBe(base.near_highest - 1);
  });

  it("resolves a figure's path in the file, a match id after matches", () => {
    const m = HYPOTHESES.matches[0];
    expect(hypothesesFigure(HYPOTHESES, `hypotheses.matches.${m.match_id}.by_frames_from_start.1.n`)).toBe(m.by_frames_from_start[1].n);
    expect(hypothesesFigure(HYPOTHESES, "hypotheses.start_bins.2.0")).toBe(HYPOTHESES.start_bins[2][0]);
  });
});
