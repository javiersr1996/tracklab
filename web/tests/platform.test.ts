import { describe, expect, it } from "vitest";
import { layerDurations } from "../lib/platform";

// `layerDurations` (task 35): on-screen seconds per layer for the flow
// animation. Five layers, one at 0 s (a step that never ran in the fixture
// selection, or a layer whose slowest step rounded to 0.0), the rest with
// real seconds -- the two properties the animation depends on: no layer
// flashes by at 0 s, and the layers always fill exactly one 8 s cycle no
// matter how the steps split.
//
// Mutation checked by hand: dropping the `minSeconds +` term (so a layer's
// share of `extra` is its whole duration) sends the 0 s layer's duration to
// 0, failing `never lets a 0 s layer disappear`; using `cycleSeconds` instead
// of `cycleSeconds - floor` as `extra` makes the durations sum to 11 s (the
// 3 s floor plus the full 8 s cycle) for five layers, failing `always fills
// exactly one cycle`.
describe("layerDurations", () => {
  it("never lets a 0 s layer disappear", () => {
    const durations = layerDurations([0, 150, 150, 0, 0]);
    expect(durations[0]).toBeCloseTo(0.6, 9);
    expect(durations[3]).toBeCloseTo(0.6, 9);
    expect(durations[4]).toBeCloseTo(0.6, 9);
  });

  it("always fills exactly one cycle, whatever the split", () => {
    const cases = [
      [0, 150, 150, 0, 0],
      [6.8, 144.5, 150.8, 119.2, 8.1],
      [0, 0, 0, 0, 0],
    ];
    for (const seconds of cases) {
      const durations = layerDurations(seconds);
      const sum = durations.reduce((total, d) => total + d, 0);
      expect(sum).toBeCloseTo(8, 9);
    }
  });
});
